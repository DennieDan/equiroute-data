# EquiRoute Data

AccessTwin / EquiRoute geospatial accessibility demo for Tech4City: a Clementi digital twin with real satellite imagery, 25 m public footpath street parts, Mapillary street-view photos, direction swapping, Supabase-backed feedback threads, and computer-vision/photo-feature evidence pins.

The active demo branch is `abel`. `main` is still the shared base branch; the public AccessTwin street-view work lives on `abel` until merged.

## Quick start: run the current AccessTwin frontend

This repo is a static HTML/Python data project, not a Node app. No `npm install` is needed for the demo frontend.

```bash
git checkout abel
git pull --ff-only origin abel
python3 -m http.server 8011 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8011/earth_accessibility.html
```

The page loads live Supabase data first and falls back to committed local JSON if Supabase is unavailable. For deterministic local-only testing, use:

```text
http://127.0.0.1:8011/earth_accessibility.html?localRegistry=1
```

Expected current demo state:

- dropdown shows about 30 public 25 m footpath street parts, not raw 3–5 m measurement segments
- Earth view uses Esri/Maxar satellite imagery with vector overlays clamped to satellite-native zoom
- Street View shows one Mapillary photo per direction when available
- `←` / `→` move to previous/next footpath; `Swap direction` only swaps direction photos
- feature scorecards hide internal IDs and avoid duplicate labels

## Prerequisites

- Python 3.10+
- LTA geospatial shapefiles placed in `GEOSPATIAL/` (not committed; see `.gitignore`)

## Setup

### 1. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a Jupyter kernel from the virtual environment

```bash
python -m ipykernel install --user --name=equiroute --display-name="Python (equiroute)"
```

In JupyterLab, select **Python (equiroute)** as the kernel when opening `persona_agent.ipynb`.

## Workflow

1. **Filter geospatial layers** — run `filter_estate.py` to crop LTA shapefiles to the Clementi bounding box and write outputs to `CLEMENTI/`.
2. **Explore & simulate** — open `persona_agent.ipynb` and run cells to load filtered layers and build route simulations.
3. **Generate persona before/after simulation output** — after placing `sim_output.json` and `threejs_3d_roads.json` in the project root, run:

```bash
python persona_simulation.py
```

This writes `sim_persona_before_after.json`, which contains persona-specific scores, bottlenecks, and the simulated impact of an accessibility intervention.

4. **Apply PERS-inspired scoring** — our benchmark basis is PERS (Pedestrian Environment Review System), the TRL/TfL pedestrian-audit framework. The prototype is not a certified PERS audit, but it maps available OSM/LTA proxy risks onto PERS-style weighted link/crossing criteria and a 0–100 RAG score:

```bash
python accessibility_scoring.py
```

5. **Generate OSM building footprints for 3D context** — fetch buildings from Overpass, save the response to `/tmp/overpass_buildings.json`, then run:

```bash
python buildings_from_overpass.py
```

This writes `buildings_clementi.geojson`, used by `maptalks_three.html` and `earth_accessibility.html` to show building context behind obstacles and improvements.

6. **Generate the Earth/street accessibility layer** — fuses LTA footpaths, kerblines, crossings, bus stops, MRT, bollards, covered linkways and overhead bridges into selectable traversable segments with ISO 21542 + ADA/PROWAG-inspired metrics:

```bash
.venv/bin/python generate_accessibility_world.py
```

This writes `accessibility_world.geojson` for the Google Earth-style street inspection UI.

`earth_accessibility.html` uses MapTalks for the geospatial map/satellite layer and Three.js for custom animated accessibility overlays: glowing route paths, wheelchair/PMA agent avatars, and intervention blocks such as ramps/shelters/bus-stop markers. Mapillary is wired as the real-life street-view provider. Mapillary requires a free client token from the Mapillary developer dashboard; enter it in the in-browser token field only. The token is stored in that browser's `localStorage` and is not committed to the repo.

The street-view navigation now uses a lightweight Google-Street-View-style node graph instead of random nearest-photo lookup. Generate the curated demo corridor registry with:

```bash
python3 scripts/street_view_registry.py --max-parts 30 --target-length-m 25
```

To harvest real Mapillary candidates and select active photos for the 30 demo street parts:

```bash
MAPILLARY_TOKEN=... python3 scripts/street_view_registry.py \
  --max-parts 30 \
  --target-length-m 25 \
  --harvest-mapillary \
  --candidate-out data/mapillary_candidates.json \
  --seed-sql supabase/seed_street_view_registry.sql
```

The harvester fetches Mapillary camera geometry/compass metadata per street part, filters both pavement-side directions (canonical road-on-right and opposite road-left/pavement-right), selects up to one active photo per direction when valid, and leaves missing-photo states intact when no suitable photo exists.

This writes `data/street_view_registry.json`, grouping the existing hidden 5 m path measurements into ~25 m street-view nodes because a single useful street photo usually covers roughly that much pedestrian path. The registry hierarchy is: **many streets → many street parts per street → one street-view node per street part → up to two active direction photos per street part**. Supabase schema/RLS/seed files live in `supabase/`; the frontend reads the Supabase street registry first and falls back to local JSON if the backend is unavailable. Feedback stays on the street part while photos can be replaced.

Run zero-shot computer-vision localization for accessibility pins:

```bash
python3 -m venv .venv-cv
. .venv-cv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
pip install transformers accelerate safetensors
PYTHONPATH=. python3 scripts/cv_localize_photo_features.py \
  --threshold 0.02 \
  --feature-match-threshold 0.02
```

This uses `google/owlvit-base-patch32` (OWL-ViT zero-shot object detection) to localize objects like tactile paving, curb ramps, covered walkways, bollards, bus stops, and crossings in active street photos. It writes `data/photo_feature_instances_cv.json`, visual QA overlays under `data/cv_overlays/`, and `supabase/seed_photo_feature_instances.sql` for the `photo_feature_instances` table.

The harvester now evaluates both compass directions for two-way roads: canonical road-on-right and opposite road-left/pavement-on-right. The frontend exposes a `Swap direction` control when both active photos exist for a street part.

Seed `accessibility_features` from the world layer with:

```bash
python3 scripts/seed_accessibility_features.py
```

This writes `supabase/seed_accessibility_features.sql`. Stable `external_id` values are formed as follows (kind + segment id only for derived ramp/tactile rows; point POIs use LTA/source IDs):

| Feature type | `external_id` pattern | Example |
| --- | --- | --- |
| kerb ramp | `{kind}_{seg_id}` | `kerb_ramp_seg_00040` |
| tactile | `{kind}_{seg_id}` | `tactile_guidance_seg_00040` |
| bus stop | `bus_stop_{BUS_STOP_N}` | `bus_stop_17239` |
| bollard / linkway | `{kind}_{OBJECTID}` | `bollard_21659` |
| MRT | `mrt_{station_name_slug}` | `mrt_clementi_mrt_station` |
| overhead bridge | `{kind}_{index}_{slug}` | `pedestrian_overhead_bridge_0_...` |

7. **View the AccessTwin frontend** — from the project root, start a static server:

```bash
python3 -m http.server 8011 --bind 127.0.0.1
```

Open:

```text
http://127.0.0.1:8011/earth_accessibility.html
```

Use `?localRegistry=1` only when you want to bypass Supabase and verify the committed local registry payload.

## Project layout

| Path                  | Description                               |
| --------------------- | ----------------------------------------- |
| `GEOSPATIAL/`         | Raw LTA shapefile downloads               |
| `CLEMENTI/`           | Filtered shapefiles for the estate        |
| `filter_estate.py`    | Crops layers to the Clementi bounding box |
| `persona_agent.ipynb` | Route graph and persona simulation        |
| `persona_simulation.py` | Generates persona before/after payloads |
| `accessibility_scoring.py` | Applies PERS-inspired scoring to the payload |
| `buildings_clementi.geojson` | OSM building footprints for map context |
| `generate_accessibility_world.py` | Creates selectable street/feature accessibility world layer |
| `accessibility_world.geojson` | Segment-level Earth/street-view accessibility metrics and POIs |
| `earth_accessibility.html` | Google Earth-style street inspection UI with selectable streets, buildings, feature layers, persona passability, and standards-based metrics |
| `maptalks_three.html` | MapTalks + Three.js prototype with before/after toggle, buildings, and obstacle/improvement markers |
| `index.html`          | Three.js 3D route viewer                  |
