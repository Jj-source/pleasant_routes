import osmnx as ox
import numpy as np

def download_graph(place: str) -> ox.Graph:
    """Download OSM walk+bike graph for a city. Returns MultiDiGraph."""

def attach_osm_indicators(G) -> None:
    """
    For each edge, attach OSM-derived indicator scores as attributes.
    Reads: highway, sidewalk, sidewalk:width,
           maxspeed, crossing count in buffer, POI density.
    Modifies G in place.
    """

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
    Proxy thermal comfort from tree node density + building height/width ratio
    within 50m buffer per edge. Attach thermal_score as edge attribute.
    Modifies G in place. Optionally joins r.sun shadow raster if available.
    POSTPONED FOR NOW
    """

def normalize_indicators(G) -> None:
    """
    Apply percentile-based min-max normalization to all indicator attributes.
    Scales each to [-1, 1] with median = 0. Modifies G in place.
    """

def save_graph(G, path: str) -> None:
    """Save enriched graph to GraphML file."""

if __name__ == "__main__":
    G = download_graph("Turin, Italy")
    attach_osm_indicators(G)
    attach_slope(G, "data/srtm/N44E007.hgt")
    attach_air_quality(G, "data/eea/pm25.tif")
    attach_thermal_comfort(G)
    normalize_indicators(G)
    save_graph(G, "backend/city_graph.graphml")