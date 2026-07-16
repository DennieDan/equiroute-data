# EquiRoute Data

Geospatial data pipeline and simulation for EquiRoute — filtering LTA layers to a local HDB estate and exploring routes in Jupyter and a 3D web viewer.

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

7. **View the 3D MVP** — from the project root, start a local server:

```bash
python -m http.server 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

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
