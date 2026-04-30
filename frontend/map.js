// init(containerId: string) → void
// Initialize Leaflet map centered on Turin, OSM tile layer.

// onMapClick(latlng: {lat, lng}) → void
// Call GET /edge, draw highlight polyline, open rating panel.
// Remove previous highlight first.

// drawRatingOverlay(ratings: GeoJSON) → void
// Color each rated segment by avg_rating (-2→red, 0→yellow, 2→green).
// High variance edges rendered with dashed style (disagreement flag).

// drawRoute(routeData: object) → void
// Draw shortest (grey) + selected alternative (colored).
// Bike mode: solid green for protected, dashed orange for shared.

// onMapMoveEnd() → void
// Fetch GET /ratings?bbox=... and call drawRatingOverlay().

// updateCoverageBar(stats: {rated, total, pct}) → void
// Update the coverage progress bar in the UI.