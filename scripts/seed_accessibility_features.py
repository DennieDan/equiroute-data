#!/usr/bin/env python3
"""Build Supabase seed SQL for accessibility_features from accessibility_world.geojson.

Maps:
  - Point POIs (bus_stop, mrt_station, bollard, covered_linkway, pedestrian_overhead_bridge)
  - Derived kerb_ramp / tactile_guidance features from route_segment metrics
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = ROOT / "accessibility_world.geojson"
DEFAULT_OUT = ROOT / "supabase" / "seed_accessibility_features.sql"

POINT_KINDS = {
    "bus_stop",
    "mrt_station",
    "bollard",
    "covered_linkway",
    "pedestrian_overhead_bridge",
}


def sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def jsonb_literal(value: Any) -> str:
    return sql_literal(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "unnamed"


def line_midpoint(coords: list[list[float]]) -> list[float]:
    if not coords:
        return [0.0, 0.0]
    if len(coords) == 1:
        return list(coords[0][:2])
    mid_i = (len(coords) - 1) // 2
    a, b = coords[mid_i], coords[min(mid_i + 1, len(coords) - 1)]
    return [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]


def point_external_id(kind: str, props: dict[str, Any], index: int) -> str:
    src = props.get("source_properties") or {}
    if kind == "bus_stop" and src.get("BUS_STOP_N") is not None:
        return f"bus_stop_{src['BUS_STOP_N']}"
    if kind == "mrt_station" and src.get("STN_NAM_DE"):
        return f"mrt_{slugify(str(src['STN_NAM_DE']))}"
    if src.get("OBJECTID") is not None:
        return f"{kind}_{src['OBJECTID']}"
    if src.get("SHAPE_LEN") is not None:
        return f"{kind}_{index}_{slugify(str(src.get('TYP_CD_DES') or kind))}"
    return f"{kind}_{index}"


def extract_accessibility_features(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert accessibility_world GeoJSON features into accessibility_features rows."""
    rows: list[dict[str, Any]] = []
    point_index = 0

    for feat in world.get("features", []):
        props = feat.get("properties") or {}
        kind = props.get("kind")
        geom = feat.get("geometry")
        if not kind or not geom:
            continue

        if kind in POINT_KINDS:
            external_id = point_external_id(kind, props, point_index)
            point_index += 1
            rows.append(
                {
                    "external_id": external_id,
                    "kind": kind,
                    "name": props.get("name") or kind.replace("_", " ").title(),
                    "geometry": geom,
                    "source": "lta_osm_proxy",
                    "properties": {
                        "selectable": props.get("selectable", True),
                        "source_properties": props.get("source_properties") or {},
                    },
                }
            )
            continue

        if kind != "route_segment":
            continue

        metrics = props.get("metrics") or {}
        seg_id = props.get("id")
        if not seg_id:
            continue
        coords = geom.get("coordinates") or []
        mid = line_midpoint(coords)
        point_geom = {"type": "Point", "coordinates": mid}
        base_props = {
            "source_segment_id": seg_id,
            "feature_type": props.get("feature_type"),
            "layer": props.get("layer"),
            "overall_accessibility_score": props.get("overall_accessibility_score"),
            "rag": props.get("rag"),
            "metrics": metrics,
            "component_scores": props.get("component_scores") or {},
        }

        if metrics.get("kerb_ramp_present"):
            rows.append(
                {
                    "external_id": f"kerb_ramp_{seg_id}",
                    "kind": "kerb_ramp",
                    "name": f"Kerb ramp on {props.get('name') or seg_id}",
                    "geometry": point_geom,
                    "source": "lta_osm_proxy",
                    "properties": {**base_props, "derived_from": "metrics.kerb_ramp_present"},
                }
            )

        if metrics.get("tactile_guidance"):
            rows.append(
                {
                    "external_id": f"tactile_guidance_{seg_id}",
                    "kind": "tactile_guidance",
                    "name": f"Tactile guidance on {props.get('name') or seg_id}",
                    "geometry": point_geom,
                    "source": "lta_osm_proxy",
                    "properties": {**base_props, "derived_from": "metrics.tactile_guidance"},
                }
            )

    return rows


def features_to_seed_sql(features: list[dict[str, Any]]) -> str:
    lines = [
        "-- Generated from accessibility_world.geojson for public.accessibility_features.",
        "-- Includes LTA/OSM point POIs plus derived kerb_ramp and tactile_guidance features.",
        "begin;",
    ]
    for feat in features:
        lines.append(
            "insert into public.accessibility_features "
            "(external_id, kind, name, geometry, source, properties) values ("
            f"{sql_literal(feat['external_id'])}, {sql_literal(feat['kind'])}, {sql_literal(feat['name'])}, "
            f"{jsonb_literal(feat['geometry'])}, {sql_literal(feat.get('source', 'lta_osm_proxy'))}, "
            f"{jsonb_literal(feat.get('properties', {}))}) "
            "on conflict (external_id) do update set "
            "kind=excluded.kind, name=excluded.name, geometry=excluded.geometry, "
            "source=excluded.source, properties=excluded.properties;"
        )
    lines.append("commit;")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    world = json.loads(args.world.read_text())
    features = extract_accessibility_features(world)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(features_to_seed_sql(features))

    by_kind: dict[str, int] = {}
    for feat in features:
        by_kind[feat["kind"]] = by_kind.get(feat["kind"], 0) + 1
    print(f"wrote {args.out} with {len(features)} accessibility_features")
    for kind, count in sorted(by_kind.items()):
        print(f"  {kind}: {count}")


if __name__ == "__main__":
    main()
