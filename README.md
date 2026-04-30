# pleasant_routes
PWA (mobile + desktop) for Turin. Users rate street segments for pleasantness, pin unsafe spots. Ratings + automatic OSM-derived scores feed a weighted routing engine.

# Pleasant Routes — Project Roadmap

## Concept

PWA (mobile + desktop) for Turin. Users rate street segments for pleasantness, pin unsafe spots. Ratings + automatic OSM-derived scores feed a weighted routing engine.

---

## Stack

|Layer|Tech|
|---|---|
|Frontend|Leaflet. Js + vanilla JS, OSM tiles (CDN)|
|Backend|Flask, 3+2 endpoints|
|Storage|SQLite (single file)|
|Routing|OSMnx + NetworkX|
|Serving|nginx + Let's Encrypt (HTTPS mandatory)|
|ML (later)|scikit-learn / LightGBM|

---

## Project Structure

```
pleasant-routes/
├── backend/
│   ├── app.py               # Flask, all endpoints
│   ├── db.py                # SQLite init + queries
│   ├── graph.py             # OSMnx load, nearest_edge, weighted routing
│   └── city_graph.graphml   # precomputed once
├── frontend/
│   ├── index.html
│   ├── map.js               # Leaflet, click→snap, highlight
│   ├── ui.js                # rating panel, onboarding, route panel
│   ├── style.css
│   ├── manifest.json        # PWA
│   └── service-worker.js    # offline cache + POST queue
├── scripts/
│   ├── build_graph.py       # one-time: OSM + indicators + SRTM + EEA
│   └── ml_score.py          # gap-filler (later)
├── data/
│   └── ratings.db
└── requirements.txt         # flask, osmnx, networkx, shapely, flask-jwt-extended(later)
```

---

## Database Schema

```sql
profiles(
  profile_id  TEXT PRIMARY KEY,  -- UUID generated client-side
  mode     TEXT,              -- cyclist|walker,
  age INTEGER,
  occupation TEXT,              -- student|worker|pensionato
  priorities  TEXT,              -- JSON array, top 3
  created_at  DATETIME
)

ratings(
  id          INTEGER PRIMARY KEY,
  u           INTEGER,           -- OSM node pair (edge key)
  v           INTEGER,
  way_id      INTEGER,           -- reference only
  profile_id  TEXT,              -- FK → profiles
  persona     TEXT,              -- denormalized for query speed
  rating      INTEGER,           -- -2 to +2
  badges      TEXT,              -- JSON: ["nature","quiet","art",...]
  unsafe      BOOLEAN,
  hour        INTEGER,           -- 0-23
  day_of_week INTEGER,           -- 0-6
  ts          DATETIME
)
```

TODO: refine the profile data to be the 20% that describes 80% of the person

---

## API Endpoints

|Method|Endpoint|Notes|
|---|---|---|
|GET| `/edge?lat=&lng=` |snap click to nearest (u, v), return GeoJSON|
|POST| `/rating` |save rating, profile_id in body|
|GET| `/ratings?bbox=` |all ratings in view for overlay|
|GET| `/route?flat=&flng=&tlat=&tlng=&persona=&mode=` |weighted GeoJSON route|
|GET| `/export?format=geojson` |full dataset export for planners|

---

## Open issues

- let user have sliders for each indicator
- let user easily switch from bike mode to walking mode
- maybe better: let's just ask the user at the beginning if they also want to contribute to the bike annotations and let them have a step more every time?
- make annotating faster: street segments are too small, find easy way to rate longer segments
- make annotating faster: reduce necessary clicks
- presets of weights for the option based on walk or bike route: details on the sidewalk score will be weighted by 0 if i am routing for a bike

## Routing

### Mode param

- `walk` — OSMnx walk graph
- `bike` — OSMnx bike graph
- `bike` — same graph, all edges annotated with `protected_pct`

### Bike route display

- Solid green line = `highway=cycleway` (physically protected)
- Dashed and point line = shared street
- Dashed = normal street
- Summary panel: `██████░░ 68% protected`

### Persona weight vectors

```python
PERSONA_WEIGHTS = {
  "cyclist": {"slope":2.0, "surface":1.5, "unsafe":2.0, "quiet":1.0},
  "walker":  {"green":1.5, "quiet":1.5, "attractive":1.0},
  "parent":  {"sidewalk":2.0, "crossing":2.0, "slope":1.5},
  "older":   {"slope":2.0, "surface":2.0, "crossing":1.5, "lit":1.0},
}
```

### Edge weight function

```python
W = length * sum(indicator_score[i] * persona_weight[i] for i in indicators)
# human rating applied as multiplier: (1 - 0.3*pleasant_score) * (1 + 0.5*unsafe_flag)
# ratings weighted by persona match
```

### Alpha optimization

Iterative search for routes ~5-10%, 10-25%, 25-50% longer than shortest. Show 2-3 alternatives with tradeoff summary.

---

## Automatic Indicators (precomputed at build time)

| Indicator            | Source                          | Method                   |
| -------------------- | ------------------------------- | ------------------------ |
| Sidewalk             | `sidewalk` OSM tag              | direct                   |
| Path width           | `width` and `sidewalk:width`    | Direct                   |
| ~~Pavement quality~~ | `surface`, `smoothness`         | direct                   |
| Slope                | SRTM DEM (free, 30m)            | one-time download + join |
| Crossings            | `highway=crossing` nodes        | count in buffer          |
| ~~Lighting~~         | `lit` tag                       | direct                   |
| Parks / green areas  | `leisure`, `landuse` polygons   | buffer intersection      |
| Trees                | `natural=tree` nodes            | density in buffer        |
| Low traffic          | `highway` type + `maxspeed`     | lookup table             |
| Pedestrian zones     | `highway=pedestrian`            | direct                   |
| Attractiveness       | POI density (cafes, shops, art) | 50m buffer count         |

All normalized to [-1, 1], percentile-based scaling, median = 0.

### Current indicator logic (build_graph.py)

- Sidewalk: `sidewalk` tag in {both, yes, left, right} -> 1.0, else 0.0
- Path width: `sidewalk:width` numeric meters, scaled.
- Maxspeed: lower is better: $1 - \frac{speed}{80}$, floored at 0
- Highway class: mapping (footway/cycleway/pedestrian positive; trunk/primary negative)
- Pedestrian zones: `highway=pedestrian` -> 1.0 else 0.0
- Low traffic: heuristic by `highway` class + maxspeed adjustment
- Crossings: count of `highway=crossing` features within 50m buffer
- POIs: count of amenities/shops/tourism features within 50m buffer
- Attractiveness: count of tourism/historic/arts/leisure POIs within 50m buffer
- Trees: count of `natural=tree` nodes within 50m buffer
- Green areas: count of park/garden/grass/forest/meadow polygons within 50m buffer

Visibility option: for POIs, attractiveness, trees, and green areas, the script can use a visibility filter (line-of-sight to feature centroid that does not intersect a building polygon). Raw buffer counts are also stored with the `_score_raw` suffix.

BONUS:

| Indicator       | Source                                                                                    | Method                   | Che ne fo                                                                          |
| --------------- | ----------------------------------------------------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------- |
| Slope           | SRTM DEM (free, 30m)                                                                      | one-time download + join | Mostro solo alert se sopra una soglia                                              |
| Lighting        | `lit` tag                                                                                 | direct                   | Se metteremo opzione per la sera                                                   |
| Air quality     | EEA annual PM2.5 raster (free)                                                            | spatial join, static     | Solo alert “questa zona ha una qualità dell’aria maggiore rispetto alle vicinanze” |
| Thermal comfort | **r.sun** in GRASS GIS — computes solar irradiance + shadow from a DEM, free, open source | GRASS GIS                |                                                                                    |


---

## ML Gap-filler (later)

- Features: all 12 automatic indicators per edge
- Target: human pleasantness rating (-2 to +2)
- Model: LightGBM, train on rated edges, predict unrated
- Bootstrap threshold: ~200-300 human ratings
- Per-persona models if data allows

---

## Frontend UX

### Map modes (top bar toggle)

- ✏️ Rate mode (default): click street → snap → highlight → panel
- 🗺️ Route mode: tap A → tap B → draw route

### Rating panel

- 👎👎 👎 👍 👍👍 (single select)
- Badge toggles: `nature` `quiet` `art` `commerce` `poor infrastructure`
- Unsafe pin toggle
- Submit → POST → close

### Route panel

- Distance + estimated time
- Protected % bar (bike mode)
- Segment coloring: green→red by pleasantness score
- 2-3 alternatives with tradeoffs

### Onboarding (skippable)

1. Persona select
2. Rank top 3 priorities
3. Profile ID shown + copy button
4. "I have a profile ID" → paste → restores profile on new device

### Overlays (always on)

- Rated segments colored by avg score
- Disagreement flag: segments with high rating variance shown with distinct style
- Coverage bar: % of Turin streets rated (gamification)

---

## Critical risks & mitigations

| Risk                                  | Mitigation                                            |
| ------------------------------------- | ----------------------------------------------------- |
| Cold start / no value without ratings | Precompute all automatic indicators before launch     |
| OSM tag incompleteness in Turin       | Audit coverage of key tags before building indicators |
| Wrong segment snapped silently        | Visual highlight confirmation mandatory before submit |
| Single VPS failure                    | Daily SQLite backup to separate location from day 1   |
| Persona bias in ratings               | Weight ratings by persona match when routing          |

---

## Build order (MVP)

1. `build_graph.py` — download OSM Turin, attach all indicators, save graphml
2. `db.py` + schema
3. `app.py` — `/edge` + `/rating` + `/ratings`
4. Leaflet map + click→snap + highlight
5. Rating panel + onboarding + profile UUID
6. Colored overlay from ratings
7. `/route` + route display + bike protected %
8. `/export`
9. Nginx + HTTPS
10. PWA manifest + service worker
11. Disagreement flag + coverage bar
12. ML gap-filler (post-launch)

---

## Effort estimate

|Component|LOC|
|---|---|
|build_graph. Py|~80|
|db. Py|~50|
|graph. Py|~80|
|app. Py|~80|
|map. Js|~80|
|ui. Js|~120|
|style. Css|~60|
|manifest + SW|~50|
|**Total**|**~600**|

---

## References

- Novack et al. (2018) — OSM pleasant routing, factor extraction methodology
- TransformTransport UX Mobility (2025) — persona clustering, 12 indicators, alpha optimization