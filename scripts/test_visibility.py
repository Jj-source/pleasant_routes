from dataclasses import dataclass
import os
import pandas as pd

import geopandas as gpd
import osmnx as ox
from shapely.geometry import LineString, Point
from shapely.ops import unary_union


@dataclass
class Counts:
    raw: int
    visible: int


def _visible_count(buffer_geom, origin_point, features: gpd.GeoDataFrame, buildings_union) -> int:
    if features.empty:
        return 0
    if buildings_union is None:
        return int(features[features.intersects(buffer_geom)].shape[0])

    sindex = features.sindex
    candidate_idx = list(sindex.intersection(buffer_geom.bounds)) if sindex else list(range(len(features)))
    if not candidate_idx:
        return 0

    candidates = features.iloc[candidate_idx]
    visible_count = 0
    for geom in candidates.geometry:
        if not geom.intersects(buffer_geom):
            continue
        target = geom.centroid
        ray = LineString([origin_point, target])
        if not buildings_union.intersects(ray):
            visible_count += 1
    return visible_count


def _count_within(buffer_geom, features: gpd.GeoDataFrame) -> int:
    if features.empty:
        return 0
    return int(features[features.intersects(buffer_geom)].shape[0])


def _safe_features_from_point(
    lat: float, lon: float, tags: dict, dist: float, label: str
) -> gpd.GeoDataFrame:
    try:
        return ox.features_from_point((lat, lon), tags=tags, dist=dist)
    except ox._errors.InsufficientResponseError:
        print(f"No matching features for {label} at {lat}, {lon} (radius {dist}m)")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def _write_geojson(layer: gpd.GeoDataFrame, out_path: str) -> None:
    if layer.empty:
        print(f"Skip {out_path}: no features")
        return
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    layer.to_crs(epsg=4326).to_file(out_path, driver="GeoJSON")
    print(f"Wrote {out_path} with {len(layer)} features")


def _layer_tagged(layer: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
        if layer.empty:
                return layer
        tagged = layer.copy()
        tagged["layer"] = name
        return tagged


def export_debug_map(
        lat: float,
        lon: float,
        radius_m: float,
        trees_path: str,
        output_dir: str,
) -> None:
        origin = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
        buffer_geom = origin.buffer(radius_m)

        crossings = _safe_features_from_point(
                lat, lon, {"highway": "crossing"}, radius_m, "crossings"
        )
        pois = _safe_features_from_point(
                lat,
                lon,
                {
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
                radius_m,
                "pois",
        )
        buildings = _safe_features_from_point(
                lat, lon, {"building": True}, radius_m, "buildings"
        )
        trees = gpd.read_file(trees_path)

        crossings = crossings.to_crs(epsg=3857) if not crossings.empty else crossings
        pois = pois.to_crs(epsg=3857) if not pois.empty else pois
        buildings = buildings.to_crs(epsg=3857) if not buildings.empty else buildings
        trees = trees.to_crs(epsg=3857) if not trees.empty else trees

        crossings = crossings[crossings.intersects(buffer_geom)] if not crossings.empty else crossings
        pois = pois[pois.intersects(buffer_geom)] if not pois.empty else pois
        buildings = buildings[buildings.intersects(buffer_geom)] if not buildings.empty else buildings
        trees = trees[trees.intersects(buffer_geom)] if not trees.empty else trees

        center = gpd.GeoDataFrame(
                {"layer": ["center"]},
                geometry=[Point(lon, lat)],
                crs="EPSG:4326",
        ).to_crs(epsg=3857)

        layers = [
                _layer_tagged(buildings, "buildings"),
                _layer_tagged(crossings, "crossings"),
                _layer_tagged(trees, "trees"),
                _layer_tagged(pois, "pois"),
                center,
        ]
        layers = [layer for layer in layers if not layer.empty]
        if not layers:
                print("No features to export")
                return

        combined = gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), crs="EPSG:3857")
        combined = combined.to_crs(epsg=4326)

        suffix = f"{lat:.6f}_{lon:.6f}_{int(radius_m)}m"
        os.makedirs(output_dir, exist_ok=True)
        geojson_path = os.path.join(output_dir, f"debug_{suffix}.geojson")
        html_path = os.path.join(output_dir, f"debug_{suffix}.html")

        combined.to_file(geojson_path, driver="GeoJSON")
        print(f"Wrote {geojson_path} with {len(combined)} features")

        html = f"""<!doctype html>
<html>
    <head>
        <meta charset=\"utf-8\" />
        <title>Visibility Debug</title>
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
        <style>
            html, body, #map {{ height: 100%; margin: 0; }}
            .legend {{
                position: absolute;
                right: 12px;
                top: 12px;
                background: white;
                padding: 8px 10px;
                border: 1px solid #ccc;
                font: 12px/1.4 sans-serif;
            }}
            .swatch {{ display: inline-block; width: 10px; height: 10px; margin-right: 6px; }}
        </style>
    </head>
    <body>
        <div id=\"map\"></div>
        <div class=\"legend\">
            <div><span class=\"swatch\" style=\"background:#9e9e9e;\"></span>buildings</div>
            <div><span class=\"swatch\" style=\"background:#1565c0;\"></span>center</div>
            <div><span class=\"swatch\" style=\"background:#e53935;\"></span>crossings</div>
            <div><span class=\"swatch\" style=\"background:#2e7d32;\"></span>trees</div>
            <div><span class=\"swatch\" style=\"background:#fb8c00;\"></span>pois</div>
        </div>
        <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
        <script>
            const map = L.map('map').setView([{lat:.6f}, {lon:.6f}], 16);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap contributors'
            }}).addTo(map);

            const colors = {{
                buildings: '#9e9e9e',
                center: '#1565c0',
                crossings: '#e53935',
                trees: '#2e7d32',
                pois: '#fb8c00'
            }};

            fetch('{os.path.basename(geojson_path)}')
                .then(resp => resp.json())
                .then(data => {{
                    const layer = L.geoJSON(data, {{
                        style: feature => {{
                            const name = feature.properties.layer || 'buildings';
                            if (name === 'buildings') {{
                                return {{ color: colors.buildings, weight: 1, fillOpacity: 0.25 }};
                            }}
                            return {{ color: colors[name] || '#000', weight: 2 }};
                        }},
                        pointToLayer: (feature, latlng) => {{
                            const name = feature.properties.layer || 'pois';
                            const color = colors[name] || '#000';
                            const radius = name === 'center' ? 6 : 4;
                            return L.circleMarker(latlng, {{
                                radius,
                                color,
                                fillColor: color,
                                fillOpacity: 0.9,
                                weight: 1
                            }});
                        }}
                    }}).addTo(map);
                    map.fitBounds(layer.getBounds().pad(0.2));
                }});
        </script>
    </body>
</html>
"""

        with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
        print(f"Wrote {html_path}")



def run(lat: float, lon: float, radius_m: float, trees_path: str) -> None:
    origin = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
    buffer_geom = origin.buffer(radius_m)

    crossings = _safe_features_from_point(
        lat, lon, {"highway": "crossing"}, radius_m, "crossings"
    )
    pois = _safe_features_from_point(
        lat,
        lon,
        {
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
        radius_m,
        "pois",
    )
    attractiveness = _safe_features_from_point(
        lat,
        lon,
        {
            "tourism": ["attraction", "museum", "artwork"],
            "historic": True,
            "amenity": ["arts_centre", "theatre", "cinema"],
        },
        radius_m,
        "attractiveness",
    )
    green_areas = _safe_features_from_point(
        lat,
        lon,
        {
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
        radius_m,
        "green_areas",
    )
    buildings = _safe_features_from_point(
        lat, lon, {"building": True}, radius_m, "buildings"
    )

    trees = gpd.read_file(trees_path)

    crossings = crossings.to_crs(epsg=3857) if not crossings.empty else crossings
    pois = pois.to_crs(epsg=3857) if not pois.empty else pois
    attractiveness = attractiveness.to_crs(epsg=3857) if not attractiveness.empty else attractiveness
    green_areas = green_areas.to_crs(epsg=3857) if not green_areas.empty else green_areas
    buildings = buildings.to_crs(epsg=3857) if not buildings.empty else buildings
    trees = trees.to_crs(epsg=3857) if not trees.empty else trees

    buildings_union = unary_union(buildings.geometry) if not buildings.empty else None

    counts = {
        "crossings": Counts(raw=_count_within(buffer_geom, crossings), visible=0),
        "pois": Counts(
            raw=_count_within(buffer_geom, pois),
            visible=_visible_count(buffer_geom, origin, pois, buildings_union),
        ),
        "attractiveness": Counts(
            raw=_count_within(buffer_geom, attractiveness),
            visible=_visible_count(buffer_geom, origin, attractiveness, buildings_union),
        ),
        "trees": Counts(
            raw=_count_within(buffer_geom, trees),
            visible=_visible_count(buffer_geom, origin, trees, buildings_union),
        ),
        "green_areas": Counts(
            raw=_count_within(buffer_geom, green_areas),
            visible=_visible_count(buffer_geom, origin, green_areas, buildings_union),
        ),
    }

    header = f"Center: {lat:.6f}, {lon:.6f} | radius: {radius_m:.0f}m"
    print("\n" + header)
    print("-" * len(header))
    print(f"Buildings: {len(buildings)}")
    if buildings.empty:
        print("Note: no building polygons in range, visibility == raw is expected")

    for key, value in counts.items():
        if key == "crossings":
            print(f"{key:<15} raw={value.raw:>4}")
            continue

        print(f"{key:<15} raw={value.raw:>4}  visible={value.visible:>4}")
        if value.visible > value.raw:
            print(f"WARNING: {key} visible > raw (check geometry/CRS)")


if __name__ == "__main__":
    coords = [
        (45.082731, 7.643349), # casa
        (45.081072, 7.642759), #farmacia
        (45.081267, 7.638263), #monte grappa
        (45.077809, 7.639926), #tesoriera lato con muro
        (45.077940, 7.649357), # vicino astra parchetto e viale
        (45.075741, 7.655840), # bernini
        (45.057460, 7.688670), # vale,
        (45.068721, 7.656339),
        (45.068560, 7.656272),
        (45.068192, 7.656476),
        (45.069376, 7.655502)
    ]
    
    c2 = [
        (45.069505, 7.655558),
        (45.069376, 7.655502),
        (45.069255, 7.655631)
    ]
    radius_m = 50.0
    trees_path = "data/alberate_geo.zip"

    #export_features(coords[0][0], coords[0][1], radius_m, trees_path, "exports")
    #export_debug_map(coords[7][0], coords[7][1], radius_m, trees_path, "exports")
    
    for lat, lon in c2:
        export_debug_map(lat, lon, radius_m, trees_path, "exports")
    
    #for lat, lon in coords:
    #    run(lat, lon, radius_m, trees_path)
        
