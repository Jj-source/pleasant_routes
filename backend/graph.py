import osmnx as ox
import networkx as nx

PERSONA_WEIGHTS = {
    "cyclist": {"slope": 2.0, "surface": 1.5, "unsafe": 2.0, "quiet": 1.0},
    "walker":  {"green": 1.5, "quiet": 1.5, "attractive": 1.0},
    "parent":  {"sidewalk": 2.0, "crossing": 2.0, "slope": 1.5},
    "older":   {"slope": 2.0, "surface": 2.0, "crossing": 1.5, "lit": 1.0},
}

def load_graph(path: str) -> nx.MultiDiGraph:
    """Load enriched GraphML. Called once at Flask startup."""

def get_node_positions(G) -> dict:
    """Return {node_id: (lat, lng)} dict for DB bbox queries."""

def nearest_edge(G, lat: float, lng: float) -> dict:
    """
    Snap coordinates to nearest graph edge using OSMnx.
    Returns {u, v, way_id, geometry: GeoJSON LineString}.
    """

def compute_edge_weight(edge_data: dict, persona: str,
                        human_rating: float | None,
                        unsafe: bool) -> float:
    """
    Combine automatic indicator scores with persona weights.
    Apply human rating multiplier if available.
    Returns scalar weight for Dijkstra.
    Formula: length * sum(indicator[i] * persona_weight[i])
             * (1 - 0.3*human_rating) * (1 + 0.5*unsafe)
    """

def build_weighted_graph(G, ratings: dict, persona: str) -> nx.MultiDiGraph:
    """
    Copy G, set weight attr on each edge via compute_edge_weight.
    ratings: {(u,v): {avg_rating, unsafe}} from DB.
    Returns weighted copy.
    """

def find_route(G_weighted, orig_lat: float, orig_lng: float,
               dest_lat: float, dest_lng: float,
               mode: str = "walk") -> dict:
    """
    Run Dijkstra on weighted graph.
    Returns GeoJSON with route + metadata:
    {geometry, length_m, protected_pct (bike), pleasantness_score}.
    """

def find_alternatives(G_weighted, orig, dest,
                      thresholds=(1.1, 1.25, 1.5)) -> list[dict]:
    """
    Iteratively adjust alpha to find routes ~10%, 25%, 50% longer
    than shortest. Returns list of route dicts.
    """

def annotate_bike_protection(route_edges: list, G) -> float:
    """
    Check highway tag per edge in route.
    Returns protected_pct = protected_length / total_length * 100.
    """