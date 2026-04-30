// initOnboarding() → void
// Check localStorage for profile_id. If missing, show onboarding panel.
// Persona select + priority ranking + UUID generation/paste.
// Save to localStorage + POST profile to /rating (first call).

// showProfileId(id: string) → void
// Display UUID with copy button. Show paste input for restore.

// openRatingPanel(edgeData: {u, v, geojson}) → void
// Show bottom panel: thumbs rating row + badge toggles + unsafe toggle + submit.

// submitRating(edgeData, rating, badges, unsafe) → void
// POST /rating with profile from localStorage.
// On success: close panel, refresh overlay.

// openRoutePanel() → void
// Show A/B input mode. On both set: call GET /route, display results.

// showRouteResult(routeData: object) → void
// Render distance, protected % bar, pleasantness score.
// List alternatives with tradeoff labels.

// toggleMode(mode: 'rate'|'route') → void
// Switch between rate and route interaction modes.