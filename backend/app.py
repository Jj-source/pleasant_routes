from flask import Flask, request, jsonify
from flask_cors import CORS
import graph, db

app = Flask(__name__)
CORS(app)
G = None  # loaded at startup

@app.before_first_request
def startup():
    """Load graph + node positions + total edge count into memory."""

@app.get("/edge")
def get_edge():
    """
    Params: lat, lng.
    Snaps to nearest edge via graph.nearest_edge().
    Returns {u, v, way_id, geojson}.
    """

@app.post("/rating")
def post_rating():
    """
    Body: {u, v, way_id, profile_id, persona, rating, badges, unsafe}.
    Saves profile if new, saves rating, returns 201.
    Reads hour + day_of_week from server timestamp.
    """

@app.get("/ratings")
def get_ratings():
    """
    Params: min_lat, min_lon, max_lat, max_lon.
    Returns GeoJSON of rated edges in bbox with avg, variance, unsafe_count.
    """

@app.get("/route")
def get_route():
    """
    Params: flat, flng, tlat, tlng, persona, mode (walk|bike).
    Fetches ratings from DB, builds weighted graph, runs routing.
    Returns {shortest, alternatives: [], metadata}.
    """

@app.get("/export")
def export():
    """
    Param: format (geojson only for now).
    Returns full rated dataset as GeoJSON for planners.
    """

if __name__ == "__main__":
    app.run(debug=True)