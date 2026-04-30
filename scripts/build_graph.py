from typing import Dict, Iterable, Tuple

import numpy as np
import osmnx as ox
import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import unary_union

def download_graph(place: str) -> ox.Graph:
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
    pois = ox.features_from_place(place, tags={"amenity": True, "shop": True, "tourism": True})
    attractiveness_pois = ox.features_from_place(
        place,
        tags={
            "tourism": ["attraction", "museum", "artwork"],
            "historic": True,
            "amenity": ["arts_centre", "theatre", "cinema"],
            "leisure": ["playground", "stadium"],
        },
    )
    trees = ox.features_from_place(place, tags={"natural": "tree"})
    green_areas = ox.features_from_place(
        place,
        tags={"leisure": ["park", "garden", "recreation_ground"], "landuse": ["grass", "forest", "meadow"]},
    )
    buildings = ox.features_from_place(place, tags={"building": True})

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
            return [0] * len(buffered)
        buffered_gdf = gpd.GeoDataFrame(geometry=buffered, crs=edges_gdf.crs)
        joined = gpd.sjoin(buffered_gdf, features, how="left", predicate="intersects")
        return joined.groupby(joined.index).size().reindex(range(len(buffered)), fill_value=0)

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

    for (u, v, k), row in edges_gdf.iterrows():
        highway = row.get("highway")
        sidewalk = row.get("sidewalk")
        sidewalk_width = row.get("sidewalk:width")
        maxspeed = row.get("maxspeed")

        # Basic heuristic scores in raw units before normalization.
        sidewalk_score = 1.0 if sidewalk in {"both", "yes", "left", "right"} else 0.0
        try:
            width_val = float(sidewalk_width) if sidewalk_width else 0.0
        except (TypeError, ValueError):
            width_val = 0.0
        width_score = min(width_val / 2.5, 1.0)

        # Lower maxspeed is better for pleasantness.
        try:
            speed_val = float(str(maxspeed).split()[0]) if maxspeed else 50.0
        except (TypeError, ValueError):
            speed_val = 50.0
        maxspeed_score = max(0.0, 1.0 - (speed_val / 80.0))

        # Highway types: prefer footway/cycleway/pedestrian, penalize trunk/primary.
        if isinstance(highway, (list, tuple)):
            highway = highway[0]
        highway_score_map = {
            "footway": 1.0,
            "cycleway": 1.0,
            "pedestrian": 0.8,
            "residential": 0.4,
            "tertiary": 0.2,
            "secondary": 0.0,
            "primary": -0.4,
            "trunk": -0.6,
        }
        highway_score = highway_score_map.get(str(highway), 0.0)

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

        G.edges[u, v, k]["sidewalk_score"] = sidewalk_score
        G.edges[u, v, k]["width_score"] = width_score
        G.edges[u, v, k]["maxspeed_score"] = maxspeed_score
        G.edges[u, v, k]["highway_score"] = highway_score
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

def normalize_indicators(G) -> None:
    """
    Apply percentile-based min-max normalization to all indicator attributes.
    Scales each to [-1, 1] with median = 0. Modifies G in place.
    """
    indicator_keys = set()
    for _, _, _, data in G.edges(keys=True, data=True):
        for key in data.keys():
            if key.endswith("_score"):
                indicator_keys.add(key)

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
    G = download_graph("Turin, Italy")
    attach_osm_indicators(G, "Turin, Italy")
    #attach_slope(G, "data/srtm/N44E007.hgt")
    #attach_air_quality(G, "data/eea/pm25.tif")
    #attach_thermal_comfort(G)
    normalize_indicators(G)
    save_graph(G, "backend/city_graph.graphml")