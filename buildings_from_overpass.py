#!/usr/bin/env python3
"""Convert an Overpass building response into frontend-friendly GeoJSON.

The MapTalks prototype uses this generated file for lightweight extruded
building footprints. Height is taken from OSM `height` or `building:levels`
when available, otherwise a deterministic default is used by building type.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def parse_height_m(tags: dict[str, str]) -> float:
    raw = tags.get("height") or tags.get("building:height")
    if raw:
        match = re.search(r"\d+(?:\.\d+)?", str(raw))
        if match:
            return max(3.0, min(180.0, float(match.group(0))))

    levels = tags.get("building:levels") or tags.get("levels")
    if levels:
        match = re.search(r"\d+(?:\.\d+)?", str(levels))
        if match:
            return max(3.0, min(180.0, float(match.group(0)) * 3.2))

    building_type = tags.get("building", "yes")
    defaults = {
        "apartments": 36.0,
        "residential": 30.0,
        "commercial": 24.0,
        "retail": 18.0,
        "mall": 22.0,
        "school": 16.0,
        "university": 18.0,
        "hospital": 24.0,
        "carpark": 18.0,
        "parking": 18.0,
        "yes": 18.0,
    }
    return defaults.get(str(building_type).lower(), 18.0)


def way_to_feature(element: dict[str, Any]) -> dict[str, Any] | None:
    geometry = element.get("geometry") or []
    if len(geometry) < 4:
        return None
    ring = [[pt["lon"], pt["lat"]] for pt in geometry]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    tags = element.get("tags", {})
    height = parse_height_m(tags)
    return {
        "type": "Feature",
        "properties": {
            "id": element.get("id"),
            "name": tags.get("name") or tags.get("addr:housename") or "Building",
            "building": tags.get("building", "yes"),
            "levels": tags.get("building:levels") or tags.get("levels"),
            "height_m": round(height, 1),
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def convert(input_path: Path, output_path: Path) -> dict[str, Any]:
    data = json.loads(input_path.read_text())
    features = []
    seen = set()
    for element in data.get("elements", []):
        if element.get("type") != "way" or element.get("id") in seen:
            continue
        seen.add(element.get("id"))
        feature = way_to_feature(element)
        if feature:
            features.append(feature)

    out = {
        "type": "FeatureCollection",
        "name": "Clementi OSM building footprints from Overpass",
        "features": features,
    }
    output_path.write_text(json.dumps(out, separators=(",", ":")))
    return out


if __name__ == "__main__":
    result = convert(Path("/tmp/overpass_buildings.json"), Path("buildings_clementi.geojson"))
    print(f"wrote buildings_clementi.geojson with {len(result['features'])} buildings")
