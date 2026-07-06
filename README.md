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
3. **View the 3D MVP** — from the project root, start a local server:

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
| `index.html`          | Three.js 3D route viewer                  |
