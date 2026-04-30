import sqlite3

DB_PATH = "data/ratings.db"

def init_db() -> None:
    """Create profiles and ratings tables if not exist."""

def save_profile(profile_id: str, persona: str, priorities: list) -> None:
    """Insert new profile row. Ignores duplicates."""

def save_rating(u: int, v: int, way_id: int, profile_id: str,
                persona: str, rating: int, badges: list,
                unsafe: bool, hour: int, day_of_week: int) -> None:
    """Insert rating row. One row per submission."""

def get_ratings_in_bbox(min_lat, min_lon, max_lat, max_lon) -> list[dict]:
    """
    Return all ratings with node coords inside bbox.
    Joins with graph node positions (passed as lookup dict).
    Returns list of {u, v, avg_rating, unsafe_count, variance, count}.
    """

def get_edge_ratings(u: int, v: int) -> list[dict]:
    """Return all individual ratings for a single edge."""

def get_coverage_stats() -> dict:
    """
    Return {rated_edges: int, total_edges: int, pct: float}.
    total_edges passed in from graph at startup.
    """

def export_all_geojson(node_positions: dict) -> dict:
    """
    Return full GeoJSON FeatureCollection of all rated edges
    with avg_rating, badges, unsafe_count as properties.
    """