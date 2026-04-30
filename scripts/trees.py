import geopandas as gpd
import osmnx as ox
from shapely.geometry import box, Point

PLACE = "via fogazzaro 27, Turin, Italy"
SIDE_METERS = 50
OUTPUT = "trees_"+"_".join(PLACE.split(",")[0].split()).lower()+"_"+str(SIDE_METERS)+"m.geojson"

lat, lon = ox.geocode(PLACE)
center = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(epsg=3857).iloc[0]
half = SIDE_METERS / 2.0
bbox = box(center.x - half, center.y - half, center.x + half, center.y + half)

gdf = gpd.read_file("data/alberate_geo.zip").to_crs(epsg=3857)
subset = gdf[gdf.intersects(bbox)].copy()

subset.to_crs(epsg=4326).to_file(OUTPUT, driver="GeoJSON")
print(f"Wrote {OUTPUT} with {len(subset)} points")