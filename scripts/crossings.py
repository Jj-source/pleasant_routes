import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point, box

PLACE = "via romagnano 4, Turin, Italy"
SIDE_METERS = 500
OUTPUT = "crossings_"+"_".join(PLACE.split(",")[0].split()).lower()+"_"+str(SIDE_METERS)+"m.geojson"

lat, lon = ox.geocode(PLACE)
center = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
half = SIDE_METERS / 2.0
bbox_3857 = box(center.x - half, center.y - half, center.x + half, center.y + half)

bbox_4326 = gpd.GeoSeries([bbox_3857], crs="EPSG:3857").to_crs(epsg=4326).iloc[0]

crossings = ox.features_from_polygon(bbox_4326, tags={"highway": "crossing"})

if crossings.empty:
    print("No crossings found in area")
else:
    crossings.to_file(OUTPUT, driver="GeoJSON")
    print(f"Wrote {OUTPUT} with {len(crossings)} features")
