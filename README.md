# JalanLens Data

JalanLens geospatial accessibility demo for Tech4City: a Clementi digital twin with real satellite imagery, ~25 m public footpath street parts, Mapillary street-view photos, direction swapping, Supabase-backed feedback threads, and persona agents that simulate how different people with disabilities experience each street part.

The active demo branch is `abel`. `main` is still the shared base branch; the public JalanLens street-view work lives on `abel` until merged.

## Quick start: run the current frontend

This repo is a static HTML/Python data project, not a Node app. No `npm install` is needed for the demo frontend.

```bash
git checkout abel
git pull --ff-only origin abel
python3 -m http.server 8011 --bind 127.0.0.1
```

Open the role-selection page first:

```text
http://127.0.0.1:8011/index.html
```

Choose **Public user** for the reporting/feedback platform, or **Authority user** for the persona-agent dashboard. The main frontend is gated by the logged-in `jalanlens_user` record in local storage, so do not open direct `?role=` URLs for demos. After login, the app redirects to:

```text
http://127.0.0.1:8011/earth_accessibility.html
```

Direct access to `earth_accessibility.html` without a stored login redirects back to `index.html`.

The page loads live Supabase street/photo data first and falls back to committed local JSON if Supabase is unavailable. For deterministic local-only testing, open the login page with a safe `next=` target, then log in:

```text
http://127.0.0.1:8011/index.html?next=earth_accessibility.html%3FlocalRegistry%3D1
```

Expected current demo state:

- dropdown shows about 30 public ~25 m footpath street parts, not raw 3–5 m measurement segments
- Earth view uses Esri/Maxar satellite imagery with vector overlays clamped to satellite-native zoom
- Street View shows one curated Mapillary photo per direction when available
- `←` / `→` move to previous/next footpath; `Swap direction` only swaps direction photos
- feature scorecards hide internal IDs and avoid duplicate labels
- persona agents show per-disability passability, start/end street-part route simulation, bottlenecks, and recommended improvements

## Current demo artifacts

| Path | Purpose |
| --- | --- |
| `index.html` | Role-selection/auth landing page for public vs authority platform |
| `earth_accessibility.html` | Main role-aware JalanLens frontend: satellite Earth view, street-view mode, scorecards, persona agents, feedback form |
| `accessibility_world.geojson` | Hidden ~5 m measurement layer with proxy accessibility metrics, POIs, and persona segment scores |
| `data/street_view_registry.json` | Public ~25 m street parts, street-view nodes, curated Mapillary active photos |
| `data/photo_feature_instances_cv.json` | OWL-ViT/zero-shot photo feature detections matched to active street photos |
| `data/persona_agent_travel_simulation.json` | Persona-agent travel simulation aggregated to public street parts |
| `buildings_clementi.geojson` | OSM building footprint context overlay |
| `feedback-form.js` | Supabase-backed feedback submission UI |
| `supabase/` | Schema, RLS, and seed SQL for live backend tables |

## Regenerate data artifacts

Most demo work does **not** require regeneration. Use these only when source layers, photos, or scoring logic change.

### 1. Accessibility world layer

Requires local LTA shapefiles under `CLEMENTI_MALL/`.

```bash
python3 generate_accessibility_world.py
```

Writes `accessibility_world.geojson`. This fuses LTA footpaths, crossings, kerb lines, bus stops, MRT, bollards, covered linkways, pickup bays, and overhead bridges into selectable measurement segments with ISO 21542 + ADA/PROWAG-inspired proxy metrics.

### 2. Street-view registry / 25 m public parts

```bash
python3 scripts/street_view_registry.py --max-parts 30 --target-length-m 25
```

To harvest real Mapillary candidates and select active photos:

```bash
MAPILLARY_TOKEN=... python3 scripts/street_view_registry.py \
  --max-parts 30 \
  --target-length-m 25 \
  --harvest-mapillary \
  --candidate-out data/mapillary_candidates.json \
  --seed-sql supabase/seed_street_view_registry.sql
```

The registry hierarchy is:

```text
many streets → many ~25 m street parts → one street-view node per street part → up to two active direction photos per part
```

The harvester filters both pavement-side directions: canonical road-on-right and opposite pavement-on-right. If no suitable photo exists, the frontend should show the missing-photo state rather than reuse an unrelated photo.

### 3. Accessibility features seed

```bash
python3 scripts/seed_accessibility_features.py
```

Writes `supabase/seed_accessibility_features.sql` from the world layer. Stable external IDs are used for feedback and photo-feature matching.

### 4. Photo feature localization

```bash
python3 -m venv .venv-cv
. .venv-cv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install transformers accelerate safetensors
PYTHONPATH=. python3 scripts/cv_localize_photo_features.py \
  --threshold 0.02 \
  --feature-match-threshold 0.02
```

This uses `google/owlvit-base-patch32` (OWL-ViT zero-shot object detection). It writes:

- `data/photo_feature_instances_cv.json`
- visual QA overlays under `data/cv_overlays/`
- `supabase/seed_photo_feature_instances.sql`

Current limitation: this is approximate CV/photo-feature evidence, not final audited ground truth. Weak detections can still need manual rejection or a stronger detector.

### 5. Persona-agent travel simulation

```bash
python3 scripts/persona_accessibility_agents.py
```

Writes `data/persona_agent_travel_simulation.json`. The script aggregates hidden 5 m segment scores into public ~25 m street parts for:

- wheelchair user
- senior with walker
- visually impaired commuter
- PMA / PMD user

For each persona it outputs passability, blockers, priority street parts, and recommended improvements such as kerb-ramp treatment, resurfacing, tactile continuation, obstruction removal, shelter, or rest points.

## Supabase update

After regenerating seeds, apply these in the Supabase SQL editor for project `khddsjemkdcgumfvkraa`:

```text
supabase/schema.sql
supabase/rls.sql
supabase/seed_street_view_registry.sql
supabase/seed_accessibility_features.sql
supabase/seed_photo_feature_instances.sql
```

Verify live counts through REST or the browser status line. The current expected frontend status is roughly:

```text
Loaded 220 street parts, 17 streets, 30 street-view nodes from Supabase
```

## Testing / verification

```bash
python3 -m unittest tests.test_street_view_registry tests.test_seed_accessibility_features -v
python3 scripts/persona_accessibility_agents.py
python3 -m http.server 8011 --bind 127.0.0.1
```

Then open `earth_accessibility.html` and verify:

- satellite imagery is visible
- dropdown has ~30 footpaths
- arrows move footpath-to-footpath
- `Swap direction` only changes direction photos
- persona-agent panel is populated
- feature scorecards do not show duplicated labels or internal IDs

## Historical / optional files

These are older exploration utilities and are not required for the current public frontend quick start:

| Path | Notes |
| --- | --- |
| `persona_agent.ipynb` | Early Jupyter exploration notebook; not needed to run the current frontend |
| `persona_simulation.py` / `sim_persona_before_after.json` | Older before/after edge simulation for previous route-graph artifacts |
| `accessibility_scoring.py` | Earlier PERS-inspired scoring utility; current frontend primarily uses `generate_accessibility_world.py` |
| `filter_estate.py`, `filter_estate_polygon.py` | Optional source-layer filtering utilities |
| `maptalks_three.html` | Older 3D viewer prototype |
| `buildings_from_overpass.py` | Optional building-footprint regeneration helper |

## Project layout

| Path | Description |
| --- | --- |
| `CLEMENTI_MALL/` | Local filtered LTA source shapefiles, not committed |
| `GEOSPATIAL/` | Raw LTA shapefile downloads, not committed |
| `scripts/` | Registry, Supabase seed, CV localization, and persona-agent generation scripts |
| `tests/` | Unit tests for registry and Supabase feature seed generation |
| `data/` | Committed frontend JSON artifacts and CV QA outputs |
| `supabase/` | Backend schema/RLS/seed SQL |
