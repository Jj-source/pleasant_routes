import logging
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import networkx as nx
import osmnx as ox
import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import unary_union

logger = logging.getLogger("build_graph")
feature_logger = logging.getLogger("build_graph.features")
progress_logger = logging.getLogger("build_graph.progress")

def download_graph(place: str) -> nx.MultiDiGraph:
    """Download OSM walk+bike graph for a city. Returns MultiDiGraph."""
    G = ox.graph_from_place(place, network_type="all", simplify=True)
    G = ox.add_edge_lengths(G)
    return G

def attach_osm_indicators(G, place: str, use_visibility: bool = True) -> None:
    """
    For each edge, attach OSM-derived indicator scores as attributes.
    Reads: highway, sidewalk, sidewalk:width,
           pedestrian zones, low-traffic,
           crossing count in buffer, POI density, trees, green areas.
    Modifies G in place.
    """
    if gpd is None:
        raise RuntimeError("geopandas is required for indicator attachment")

    edges_gdf = ox.graph_to_gdfs(G, nodes=False, fill_edge_geometry=True)
    edges_gdf = edges_gdf.to_crs(epsg=3857)

    # Build feature layers for crossings, POIs, trees, green areas, and buildings.
    crossings = ox.features_from_place(place, tags={"highway": "crossing"})
    # Sociability POIs (Novack Table 1).
    pois = ox.features_from_place(
        place,
        tags={
            "amenity": ["cafe", "bar", "pub", "restaurant"],
            "shop": [
                "bakery",
                "convenience",
                "supermarket",
                "mall",
                "department_store",
                "clothes",
                "fashion",
                "shoes",
            ],
            "leisure": ["fitness_centre"],
        },
    )
    attractiveness_pois = ox.features_from_place(
        place,
        tags={
            "tourism": ["attraction", "museum", "artwork"],
            "historic": True,
            "amenity": ["arts_centre", "theatre", "cinema"],
        },
    )
    trees = ox.features_from_place(place, tags={"natural": "tree"})
    green_areas = ox.features_from_place(
        place,
        tags={
            "leisure": ["park", "garden", "recreation_ground", "nature_reserve", "pitch"],
            "landuse": [
                "grass",
                "forest",
                "meadow",
                "greenfield",
                "allotments",
                "cemetery",
                "orchard",
                "village_green",
                "vineyard",
            ],
            "natural": ["wood", "scrub", "grassland", "wetland", "heath"],
            "amenity": ["grave_yard"],
            "tourism": ["camp_site"],
        },
    )
    buildings = ox.features_from_place(place, tags={"building": True})

    feature_logger.info(
        "Fetched features: crossings=%s pois=%s attractiveness=%s trees=%s green=%s buildings=%s",
        len(crossings),
        len(pois),
        len(attractiveness_pois),
        len(trees),
        len(green_areas),
        len(buildings),
    )

    crossings = crossings.to_crs(edges_gdf.crs) if not crossings.empty else crossings
    pois = pois.to_crs(edges_gdf.crs) if not pois.empty else pois
    attractiveness_pois = (
        attractiveness_pois.to_crs(edges_gdf.crs) if not attractiveness_pois.empty else attractiveness_pois
    )
    trees = trees.to_crs(edges_gdf.crs) if not trees.empty else trees
    green_areas = green_areas.to_crs(edges_gdf.crs) if not green_areas.empty else green_areas
    buildings = buildings.to_crs(edges_gdf.crs) if not buildings.empty else buildings

    buildings_union = unary_union(buildings.geometry) if not buildings.empty else None

    # Precompute buffers and midpoints for spatial counts.
    edges_gdf["buffer_50m"] = edges_gdf.geometry.buffer(50)
    edges_gdf["midpoint"] = edges_gdf.geometry.interpolate(0.5, normalized=True)

    def _count_within(buffered: gpd.GeoSeries, features: gpd.GeoDataFrame) -> Iterable[int]:
        if features.empty:
            return gpd.Series(0, index=buffered.index)
        buffered_gdf = gpd.GeoDataFrame(geometry=buffered, crs=edges_gdf.crs, index=buffered.index)
        joined = gpd.sjoin(buffered_gdf, features, how="left", predicate="intersects")
        return joined.groupby(joined.index).size().reindex(buffered.index, fill_value=0)

    def _visible_count(buffer_geom, origin_point, features: gpd.GeoDataFrame) -> int:
        if features.empty:
            return 0
        if buildings_union is None:
            return int(features[features.intersects(buffer_geom)].shape[0])

        sindex = features.sindex
        candidate_idx = list(sindex.intersection(buffer_geom.bounds)) if sindex else list(features.index)
        if not candidate_idx:
            return 0
        candidates = features.loc[candidate_idx]
        visible_count = 0
        for geom in candidates.geometry:
            if not geom.intersects(buffer_geom):
                continue
            target = geom.centroid
            ray = LineString([origin_point, target])
            if not buildings_union.intersects(ray):
                visible_count += 1
        return visible_count

    crossing_counts = _count_within(edges_gdf["buffer_50m"], crossings)
    poi_counts_raw = _count_within(edges_gdf["buffer_50m"], pois)
    attractiveness_counts_raw = _count_within(edges_gdf["buffer_50m"], attractiveness_pois)
    tree_counts_raw = _count_within(edges_gdf["buffer_50m"], trees)
    green_counts_raw = _count_within(edges_gdf["buffer_50m"], green_areas)

    total_edges = len(edges_gdf)
    tag_presence = {
        "highway": edges_gdf["highway"].notna().sum(),
        "sidewalk": edges_gdf["sidewalk"].notna().sum(),
        "sidewalk:width": edges_gdf["sidewalk:width"].notna().sum(),
        "maxspeed": edges_gdf["maxspeed"].notna().sum(),
        "width": edges_gdf.get("width", gpd.Series([], dtype=object)).notna().sum(),
        "surface": edges_gdf.get("surface", gpd.Series([], dtype=object)).notna().sum(),
        "smoothness": edges_gdf.get("smoothness", gpd.Series([], dtype=object)).notna().sum(),
    }
    feature_logger.info("Edge tag coverage out of %s: %s", total_edges, tag_presence)

    def _count_positive(values: Iterable[int]) -> int:
        return int(np.count_nonzero(np.asarray(values)))

    feature_logger.info(
        "Raw buffer counts (edges with >=1): crossings=%s pois=%s attractiveness=%s trees=%s green=%s",
        _count_positive(crossing_counts),
        _count_positive(poi_counts_raw),
        _count_positive(attractiveness_counts_raw),
        _count_positive(tree_counts_raw),
        _count_positive(green_counts_raw),
    )

    visible_positive = {
        "poi": 0,
        "attractiveness": 0,
        "tree": 0,
        "green": 0,
    }

    progress_step = max(1, total_edges // 20)
    for idx, ((u, v, k), row) in enumerate(edges_gdf.iterrows(), start=1):
        if idx == 1 or idx % progress_step == 0 or idx == total_edges:
            percent = (idx / total_edges) * 100
            progress_logger.info("Edge processing: %s/%s (%.0f%%)", idx, total_edges, percent)
        highway = row.get("highway")
        if isinstance(highway, (list, tuple)):
            highway = highway[0]
        sidewalk = row.get("sidewalk")
        sidewalk_width = row.get("sidewalk:width")
        width = row.get("width")
        maxspeed = row.get("maxspeed")

        # Basic heuristic scores in raw units before normalization.
        sidewalk_score = 1.0 if sidewalk in {"both", "yes", "left", "right"} else 0.0
        try:
            if str(highway) in {"pedestrian", "footway", "living_street"}:
                width_val = float(width) if width else 0.0
                sidewalk_score = 1.0
            else:
                width_val = float(sidewalk_width) if sidewalk_width else 0.0
        except (TypeError, ValueError):
            width_val = 0.0
            
        if width_val == 0.0:
            width_score = 0.5
        elif width_val < 1.5:
            width_score = 0.0
        elif width_val < 2:
            width_score = 0.2
        elif width_val < 2.5:
            width_score = 0.4
        elif width_val < 3.0:
            width_score = 0.6
        elif width_val < 4.0:
            width_score = 0.8
        else:
            width_score = 1.0

        # Lower maxspeed is better for pleasantness.
        try:
            speed_val = float(str(maxspeed).split()[0]) if maxspeed else 50.0
        except (TypeError, ValueError):
            speed_val = 50.0
        maxspeed_score = max(0.0, 1.0 - (speed_val / 50.0))

        pedestrian_score = 1.0 if str(highway) == "pedestrian" else 0.0

        # Low traffic: simple heuristic from highway class + speed.
        low_traffic_score = 0.0
        if str(highway) in {"footway", "path", "cycleway", "pedestrian", "living_street"}:
            low_traffic_score = 1.0
        elif str(highway) in {"residential", "service"}:
            low_traffic_score = 0.6
        elif str(highway) in {"tertiary"}:
            low_traffic_score = 0.3
        elif str(highway) in {"secondary", "primary", "trunk"}:
            low_traffic_score = 0.0
        if speed_val <= 30:
            low_traffic_score = min(1.0, low_traffic_score + 0.2)
        elif speed_val >= 70:
            low_traffic_score = max(0.0, low_traffic_score - 0.2)

        crossing_score = float(crossing_counts[row.name])
        buffer_geom = row["buffer_50m"]
        origin_point = row["midpoint"]
        poi_raw = float(poi_counts_raw[row.name])
        attractiveness_raw = float(attractiveness_counts_raw[row.name])
        tree_raw = float(tree_counts_raw[row.name])
        green_raw = float(green_counts_raw[row.name])

        if use_visibility:
            poi_visible = float(_visible_count(buffer_geom, origin_point, pois))
            attractiveness_visible = float(
                _visible_count(buffer_geom, origin_point, attractiveness_pois)
            )
            tree_visible = float(_visible_count(buffer_geom, origin_point, trees))
            green_visible = float(_visible_count(buffer_geom, origin_point, green_areas))
        else:
            poi_visible = poi_raw
            attractiveness_visible = attractiveness_raw
            tree_visible = tree_raw
            green_visible = green_raw

        if poi_visible > 0:
            visible_positive["poi"] += 1
        if attractiveness_visible > 0:
            visible_positive["attractiveness"] += 1
        if tree_visible > 0:
            visible_positive["tree"] += 1
        if green_visible > 0:
            visible_positive["green"] += 1

        G.edges[u, v, k]["sidewalk_score"] = sidewalk_score
        G.edges[u, v, k]["width_score"] = width_score
        G.edges[u, v, k]["maxspeed_score"] = maxspeed_score
        G.edges[u, v, k]["pedestrian_score"] = pedestrian_score
        G.edges[u, v, k]["low_traffic_score"] = low_traffic_score
        G.edges[u, v, k]["crossing_score"] = crossing_score
        G.edges[u, v, k]["poi_score"] = poi_visible
        G.edges[u, v, k]["attractiveness_score"] = attractiveness_visible
        G.edges[u, v, k]["tree_score"] = tree_visible
        G.edges[u, v, k]["green_score"] = green_visible
        G.edges[u, v, k]["poi_score_raw"] = poi_raw
        G.edges[u, v, k]["attractiveness_score_raw"] = attractiveness_raw
        G.edges[u, v, k]["tree_score_raw"] = tree_raw
        G.edges[u, v, k]["green_score_raw"] = green_raw

    feature_logger.info(
        "Visible counts (edges with >=1): poi=%s attractiveness=%s tree=%s green=%s",
        visible_positive["poi"],
        visible_positive["attractiveness"],
        visible_positive["tree"],
        visible_positive["green"],
    )

def attach_slope(G, srtm_path: str) -> None:
    """
    Load SRTM .hgt raster, compute elevation diff between edge nodes.
    Attach slope (%) as edge attribute. Modifies G in place.
    POSTPONED FOR NOW
    """

def attach_air_quality(G, eea_raster_path: str) -> None:
    """
    Spatially join EEA PM2.5 annual mean raster to edges by midpoint.
    Attach pm25_score (normalized -1 to 1) as edge attribute.
    Modifies G in place.
    POSTPONED FOR NOW
    """

def attach_thermal_comfort(G) -> None:
    """
    Attach thermal_score as edge attribute.
    Modifies G in place. Optionally joins r.sun shadow raster if available.
    Maybe open data?
    POSTPONED FOR NOW
    """

def normalize_indicators(
    G,
    bounded_01_keys: Iterable[str] | None = None,
    skip_keys: Iterable[str] | None = None,
) -> None:
    """
    Apply percentile-based min-max normalization to all indicator attributes.
    Scales each to [-1, 1] with median = 0. Modifies G in place.
    """
    skip = set(skip_keys or [])
    bounded_01 = set(bounded_01_keys or [])
    indicator_keys = set()
    for _, _, _, data in G.edges(keys=True, data=True):
        for key in data.keys():
            if key.endswith("_score"):
                indicator_keys.add(key)

    indicator_keys -= skip

    # Normalize known bounded indicators to [-1, 1].
    for key in bounded_01:
        if key not in indicator_keys:
            continue
        for _, _, _, data in G.edges(keys=True, data=True):
            val = data.get(key)
            if val is None:
                continue
            val = float(np.clip(val, 0.0, 1.0))
            data[key] = (2.0 * val) - 1.0

    indicator_keys -= bounded_01

    for key in indicator_keys:
        values = []
        for _, _, _, data in G.edges(keys=True, data=True):
            val = data.get(key)
            if val is not None:
                values.append(float(val))

        if not values:
            continue

        p5 = np.nanpercentile(values, 5)
        p95 = np.nanpercentile(values, 95)
        median = np.nanmedian(values)

        denom_low = median - p5 if median != p5 else 1.0
        denom_high = p95 - median if p95 != median else 1.0

        for u, v, k, data in G.edges(keys=True, data=True):
            val = data.get(key)
            if val is None:
                continue
            if val <= median:
                scaled = (val - median) / denom_low
            else:
                scaled = (val - median) / denom_high
            data[key] = float(np.clip(scaled, -1.0, 1.0))

def save_graph(G, path: str) -> None:
    """Save enriched graph to GraphML file."""
    ox.save_graphml(G, filepath=path)

if __name__ == "__main__":
    ## logging
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    date_format = "%H:%M:%S"

    info_handler = logging.FileHandler(Path("build_graph_info.log"))
    info_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    info_handler.setLevel(logging.INFO)

    feature_handler = logging.FileHandler(Path("build_graph_features.log"))
    feature_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    feature_handler.setLevel(logging.INFO)

    progress_handler = logging.StreamHandler()
    progress_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    progress_handler.setLevel(logging.INFO)

    logger.setLevel(logging.INFO)
    logger.addHandler(info_handler)

    feature_logger.setLevel(logging.INFO)
    feature_logger.addHandler(feature_handler)

    progress_logger.setLevel(logging.INFO)
    progress_logger.addHandler(progress_handler)
    
    ##
    
    start = time.perf_counter()
    logger.info("Starting graph build")
    logger.info("Step 1/4: download graph")
    G = download_graph("Turin, Italy")
    
    logger.info("Step 2/4: attach OSM indicators")
    attach_osm_indicators(G, "Turin, Italy")
    
    #attach_slope(G, "data/srtm/N44E007.hgt")
    #attach_air_quality(G, "data/eea/pm25.tif")
    #attach_thermal_comfort(G)
    
    logger.info("Step 3/4: normalize indicators")
    bounded_01 = {
        "sidewalk_score",
        "width_score",
        "maxspeed_score",
        "pedestrian_score",
        "low_traffic_score",
    }
    skip_normalization = {}
    normalize_indicators(G, bounded_01_keys=bounded_01, skip_keys=skip_normalization)
    
    logger.info("Step 4/4: save graph")
    output_path = Path("backend/city_graph.graphml")
    save_graph(G, str(output_path))
    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info("Saved graph: %s (%.1f MB)", output_path, size_mb)
    elapsed = time.perf_counter() - start
    logger.info("Completed in %.1f seconds", elapsed)