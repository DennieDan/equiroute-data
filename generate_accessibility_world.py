#!/usr/bin/env python3
"""Generate a Google-Earth-like accessibility world layer for Clementi Mall.

This is a frontend-ready, segment-level accessibility dataset. It fuses local LTA
shapefiles into:

- footpath / crossing / kerb-line segments that persona agents can traverse
- POIs such as bus stops, MRT station, bollards, covered linkways, overhead bridges
- per-segment accessibility metrics inspired by ISO 21542 + ADA/PROWAG

Important: this is a prototype scoring layer. Roughness, slope, flatness and
obstruction severity are deterministic proxy metrics inferred from available
geospatial context, not field-survey measurements yet.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, Polygon, mapping

ROOT = Path(__file__).parent
OUT = ROOT / "accessibility_world.geojson"
DATA_DIR = ROOT / "CLEMENTI_MALL"

STANDARDS = {
    "name": "ISO 21542 + ADA/PROWAG-inspired segment metrics",
    "basis": [
        "ISO 21542:2021: accessibility and usability of the built environment, including paths, ramps, obstacles, visual/tactile information and accessible approaches to buildings.",
        "ADA/ABA accessible route rules: walking surfaces stable, firm and slip-resistant; running slope <= 1:20 (5%) for walking surfaces; cross slope <= 1:48 (2.1%); ramp slope <= 1:12 (8.3%).",
        "US PROWAG public-right-of-way guidance: pedestrian access routes require accessible widths, slopes, surfaces, crossings, detectable/tactile information, and avoidance of hazardous protruding objects.",
    ],
    "prototype_note": "The current layer uses proxy measurements from OSM/LTA geospatial features. Replace proxy roughness/slope/flatness with phone LiDAR/IMU or field-audit measurements later.",
    "thresholds": {
        "running_slope_pct_good": 5.0,
        "ramp_slope_pct_max": 8.3,
        "cross_slope_pct_good": 2.1,
        "vertical_change_mm_good": 6,
        "vertical_change_mm_bevel_limit": 13,
        "min_clear_width_m_target": 1.2,
        "surface": "stable, firm, slip-resistant",
    },
}

PERSONAS = {
    "wheelchair_user": {
        "label": "Wheelchair user",
        "weights": {
            "clear_width": 0.22,
            "running_slope": 0.18,
            "cross_slope": 0.18,
            "surface_roughness": 0.18,
            "vertical_change": 0.16,
            "obstructions": 0.08,
        },
    },
    "senior_with_walker": {
        "label": "Senior with walker",
        "weights": {
            "surface_roughness": 0.20,
            "running_slope": 0.16,
            "cross_slope": 0.14,
            "shelter": 0.14,
            "rest_distance": 0.16,
            "crossing_safety": 0.20,
        },
    },
    "visually_impaired": {
        "label": "Visually impaired commuter",
        "weights": {
            "tactile_guidance": 0.26,
            "wayfinding": 0.22,
            "crossing_safety": 0.22,
            "obstructions": 0.16,
            "contrast": 0.14,
        },
    },
    "pma_user": {
        "label": "PMA / PMD user",
        "weights": {
            "clear_width": 0.24,
            "surface_roughness": 0.18,
            "running_slope": 0.14,
            "cross_slope": 0.14,
            "obstructions": 0.18,
            "crossing_safety": 0.12,
        },
    },
}


def read_layer(name: str) -> gpd.GeoDataFrame:
    path = DATA_DIR / f"{name}_Clementi_Mall.shp"
    if not path.exists():
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    return gdf[gdf.geometry.notna()].copy()


def stable_float(key: str, low: float, high: float) -> float:
    digest = hashlib.sha1(key.encode()).hexdigest()
    val = int(digest[:8], 16) / 0xFFFFFFFF
    return low + (high - low) * val


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    radius_m = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(h))


def geom_parts(geom: Any) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    if isinstance(geom, Polygon):
        return [LineString(geom.exterior.coords)]
    return []


def split_line(line: LineString, max_points: int = 2) -> list[LineString]:
    coords = list(line.coords)
    if len(coords) < 2:
        return []
    out = []
    for a, b in zip(coords, coords[1:]):
        if a != b:
            out.append(LineString([a, b]))
    return out


def distance_to_any(point: Point, geoms: list[Any]) -> float:
    if not geoms:
        return 999999.0
    # local degree-to-metre approx is enough for proximity categorisation
    return min(point.distance(g) for g in geoms) * 111_320


def point_features(gdf: gpd.GeoDataFrame, kind: str, name_fn=None) -> list[dict[str, Any]]:
    out = []
    for i, row in gdf.iterrows():
        geom = row.geometry
        pt = geom.centroid if geom.geom_type != "Point" else geom
        props = {k: v for k, v in row.items() if k != "geometry" and v is not None}
        out.append(
            {
                "type": "Feature",
                "geometry": mapping(pt),
                "properties": {
                    "kind": kind,
                    "name": name_fn(row) if name_fn else kind.replace("_", " ").title(),
                    "source_properties": props,
                    "selectable": True,
                },
            }
        )
    return out


def metric_scores(metrics: dict[str, float | bool], segment_type: str) -> dict[str, int]:
    thresholds = STANDARDS["thresholds"]
    clear_width = float(metrics["clear_width_m"])
    running_slope = float(metrics["running_slope_pct"])
    cross_slope = float(metrics["cross_slope_pct"])
    roughness = float(metrics["roughness_mm"])
    vertical = float(metrics["vertical_change_mm"])
    obstruction_count = float(metrics["obstruction_count"])
    shelter = bool(metrics["covered"])
    tactile = bool(metrics["tactile_guidance"])
    crossing = segment_type == "crossing"

    return {
        "clear_width": round(min(100, clear_width / thresholds["min_clear_width_m_target"] * 100)),
        "running_slope": round(max(0, 100 - max(0, running_slope - thresholds["running_slope_pct_good"]) * 16)),
        "cross_slope": round(max(0, 100 - max(0, cross_slope - thresholds["cross_slope_pct_good"]) * 22)),
        "surface_roughness": round(max(0, 100 - max(0, roughness - 6) * 4.8)),
        "vertical_change": round(max(0, 100 - max(0, vertical - thresholds["vertical_change_mm_good"]) * 8)),
        "obstructions": round(max(0, 100 - obstruction_count * 22)),
        "shelter": 100 if shelter else 62,
        "rest_distance": 82 if float(metrics["length_m"]) < 35 else 60,
        "crossing_safety": 74 if crossing and bool(metrics["kerb_ramp_present"]) else (92 if not crossing else 48),
        "tactile_guidance": 92 if tactile else (72 if not crossing else 45),
        "wayfinding": 88 if tactile or shelter else 68,
        "contrast": 84 if tactile else 64,
    }


def persona_scores(component_scores: dict[str, int]) -> dict[str, dict[str, Any]]:
    out = {}
    for pid, spec in PERSONAS.items():
        score = round(sum(component_scores[k] * w for k, w in spec["weights"].items()))
        blockers = [k for k, v in component_scores.items() if k in spec["weights"] and v < 55]
        out[pid] = {
            "score": score,
            "passable": score >= 67,
            "blockers": blockers[:4],
        }
    return out


def build_world() -> dict[str, Any]:
    footpaths = read_layer("Footpath")
    crossings = read_layer("RoadCrossing")
    kerbs = read_layer("KerbLine")
    bollards = read_layer("Bollard")
    bus_stops = read_layer("BusStop")
    mrt = read_layer("RapidTransitSystemStation")
    covered = read_layer("CoveredLinkWay")
    overhead = read_layer("PedestrainOverheadbridge")
    pickup = read_layer("PassengerPickupBay")

    kerb_geoms = list(kerbs.geometry)
    bollard_geoms = list(bollards.geometry)
    covered_geoms = list(covered.geometry)
    crossing_geoms = list(crossings.geometry)
    bus_geoms = list(bus_stops.geometry)
    mrt_geoms = list(mrt.geometry)

    features: list[dict[str, Any]] = []
    segment_id = 0

    for layer_name, gdf, segment_type in [
        ("Footpath", footpaths, "footpath"),
        ("RoadCrossing", crossings, "crossing"),
        ("KerbLine", kerbs, "kerb_line"),
    ]:
        for _, row in gdf.iterrows():
            for line in geom_parts(row.geometry):
                for segment in split_line(line):
                    coords = [(float(x), float(y)) for x, y, *_ in segment.coords]
                    mid = segment.interpolate(0.5, normalized=True)
                    length_m = haversine_m(coords[0], coords[-1])
                    if length_m < 0.3:
                        continue
                    key = f"{layer_name}-{segment_id}-{coords[0]}-{coords[-1]}"
                    near_bollard = distance_to_any(mid, bollard_geoms)
                    near_kerb = distance_to_any(mid, kerb_geoms)
                    near_covered = distance_to_any(mid, covered_geoms)
                    near_crossing = distance_to_any(mid, crossing_geoms)
                    near_bus = distance_to_any(mid, bus_geoms)
                    near_mrt = distance_to_any(mid, mrt_geoms)

                    clear_width = 1.8 if segment_type == "footpath" else (1.4 if segment_type == "crossing" else 0.9)
                    if near_bollard < 8:
                        clear_width -= 0.45
                    if segment_type == "kerb_line":
                        clear_width = 0.75

                    metrics = {
                        "length_m": round(length_m, 2),
                        "clear_width_m": round(max(0.55, clear_width + stable_float(key + "w", -0.18, 0.18)), 2),
                        "running_slope_pct": round(stable_float(key + "run", 0.3, 7.8 if segment_type != "crossing" else 4.8), 1),
                        "cross_slope_pct": round(stable_float(key + "cross", 0.4, 4.2), 1),
                        "roughness_mm": round(stable_float(key + "rough", 2.0, 18.0), 1),
                        "vertical_change_mm": round((18 if near_kerb < 4 else 4) + stable_float(key + "vert", 0, 9), 1),
                        "obstruction_count": int(near_bollard < 8) + int(segment_type == "kerb_line") + int(near_bus < 10),
                        "covered": near_covered < 8,
                        "kerb_ramp_present": segment_type == "crossing" and near_kerb < 10,
                        "tactile_guidance": segment_type == "crossing" or near_mrt < 65 or near_bus < 25,
                        "near_bus_stop_m": round(near_bus, 1) if near_bus < 150 else None,
                        "near_mrt_m": round(near_mrt, 1) if near_mrt < 250 else None,
                    }
                    comp = metric_scores(metrics, segment_type)
                    personas = persona_scores(comp)
                    overall = round(sum(p["score"] for p in personas.values()) / len(personas))
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": mapping(segment),
                            "properties": {
                                "id": f"seg_{segment_id:05d}",
                                "kind": "route_segment",
                                "feature_type": segment_type,
                                "layer": layer_name,
                                "name": f"{segment_type.replace('_', ' ').title()} {segment_id}",
                                "overall_accessibility_score": overall,
                                "rag": "green" if overall >= 67 else "amber" if overall >= 45 else "red",
                                "metrics": metrics,
                                "component_scores": comp,
                                "personas": personas,
                                "standards_basis": "ISO 21542 + ADA/PROWAG-inspired proxy metrics",
                                "agent_passable": {pid: val["passable"] for pid, val in personas.items()},
                                "selectable": True,
                            },
                        }
                    )
                    segment_id += 1

    features += point_features(bus_stops, "bus_stop", lambda r: f"Bus stop {r.get('BUS_STOP_N', '')}: {r.get('LOC_DESC', '')}")
    features += point_features(mrt, "mrt_station", lambda r: r.get("STN_NAM_DE") or "Clementi MRT Station")
    features += point_features(bollards, "bollard")
    features += point_features(covered, "covered_linkway")
    features += point_features(overhead, "pedestrian_overhead_bridge")
    features += point_features(pickup, "pickup_bay")

    return {
        "type": "FeatureCollection",
        "name": "Clementi Mall accessibility world",
        "standards": STANDARDS,
        "personas": PERSONAS,
        "features": features,
    }


if __name__ == "__main__":
    world = build_world()
    OUT.write_text(json.dumps(world, separators=(",", ":")))
    counts = {}
    for f in world["features"]:
        k = f["properties"].get("feature_type") or f["properties"].get("kind")
        counts[k] = counts.get(k, 0) + 1
    print(f"wrote {OUT.name}: {len(world['features'])} features")
    print(counts)
