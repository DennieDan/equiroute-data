#!/usr/bin/env python3
"""Build AccessTwin street-view node graph and photo registry.

This is the lightweight Google-Street-View-like layer for the hack demo. It
converts raw 5 m route segments into stable 8-10 m street parts, then creates a
prev/next street-view node graph. Mapillary/crowd photos can be attached later;
the graph itself is deterministic and safe to commit.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = ROOT / "accessibility_world.geojson"
DEFAULT_OUT = ROOT / "data" / "street_view_registry.json"


def angle_diff(a: float, b: float) -> float:
    """Return smallest signed difference a-b in degrees, in [-180, 180)."""
    return ((a - b + 540) % 360) - 180


def haversine_m(a: Iterable[float], b: Iterable[float]) -> float:
    lon1, lat1 = list(a)[:2]
    lon2, lat2 = list(b)[:2]
    radius_m = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(h))


def bearing_deg(a: Iterable[float], b: Iterable[float]) -> float:
    lon1, lat1 = [math.radians(x) for x in list(a)[:2]]
    lon2, lat2 = [math.radians(x) for x in list(b)[:2]]
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def midpoint(coords: list[list[float]]) -> list[float]:
    if not coords:
        return [0.0, 0.0]
    lon = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return [lon, lat]


def segment_length(feature: dict[str, Any]) -> float:
    metrics = feature.get("properties", {}).get("metrics", {})
    if isinstance(metrics.get("length_m"), (int, float)):
        return float(metrics["length_m"])
    coords = feature.get("geometry", {}).get("coordinates", [])
    return sum(haversine_m(a, b) for a, b in zip(coords, coords[1:]))


def segment_coords(feature: dict[str, Any]) -> list[list[float]]:
    return feature.get("geometry", {}).get("coordinates", [])


def merge_scores(features: list[dict[str, Any]]) -> dict[str, Any]:
    if not features:
        return {}
    lengths = [max(0.1, segment_length(f)) for f in features]
    total = sum(lengths)
    scores = [f.get("properties", {}).get("overall_accessibility_score", 0) for f in features]
    return {
        "overall_accessibility_score": round(sum(s * l for s, l in zip(scores, lengths)) / total),
        "source_segment_count": len(features),
    }


def group_segments_into_street_parts(
    segments: list[dict[str, Any]],
    target_length_m: float = 10.0,
    max_parts: int | None = None,
) -> list[dict[str, Any]]:
    """Group contiguous 5 m route segments into 8-10 m street-photo parts."""
    route_segments = [s for s in segments if s.get("properties", {}).get("kind") == "route_segment"]
    parts: list[dict[str, Any]] = []
    bucket: list[dict[str, Any]] = []
    bucket_len = 0.0

    def flush() -> None:
        nonlocal bucket, bucket_len
        if not bucket:
            return
        coords: list[list[float]] = []
        for f in bucket:
            segc = segment_coords(f)
            if not coords:
                coords.extend(segc)
            else:
                coords.extend(segc[1:] if coords[-1] == segc[0] else segc)
        start, end = coords[0], coords[-1]
        mid = midpoint(coords)
        part_id = f"street_part_{len(parts):04d}"
        source = merge_scores(bucket)
        parts.append(
            {
                "id": part_id,
                "route_segment_ids": [f["properties"].get("id", f"seg_{i}") for i, f in enumerate(bucket)],
                "geometry": {"type": "LineString", "coordinates": coords},
                "midpoint": mid,
                "length_m": round(bucket_len, 2),
                "direction_bearing_deg": round(bearing_deg(start, end), 2),
                "desired_orientation": "road_right",
                "metrics": {
                    "source_segment_count": source["source_segment_count"],
                    "overall_accessibility_score": source["overall_accessibility_score"],
                },
            }
        )
        bucket = []
        bucket_len = 0.0

    for feature in route_segments:
        bucket.append(feature)
        bucket_len += segment_length(feature)
        if bucket_len >= target_length_m:
            flush()
            if max_parts and len(parts) >= max_parts:
                break
    if bucket and (not max_parts or len(parts) < max_parts):
        flush()
    return parts


def candidate_coord(candidate: dict[str, Any]) -> list[float] | None:
    geom = candidate.get("computed_geometry") or candidate.get("geometry") or {}
    coords = geom.get("coordinates")
    if isinstance(coords, list) and len(coords) >= 2:
        return [float(coords[0]), float(coords[1])]
    return None


def candidate_heading(candidate: dict[str, Any]) -> float | None:
    val = candidate.get("computed_compass_angle", candidate.get("compass_angle"))
    return float(val) if isinstance(val, (int, float)) else None


def captured_ts(candidate: dict[str, Any]) -> float:
    raw = candidate.get("captured_at") or candidate.get("capturedAt") or "1970-01-01T00:00:00Z"
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def choose_best_photo(
    candidates: list[dict[str, Any]],
    midpoint: list[float],
    desired_heading_deg: float,
    max_heading_delta: float = 35,
) -> dict[str, Any] | None:
    """Choose best candidate by direction first, then distance/recency/pano."""
    scored: list[tuple[float, dict[str, Any], bool, float, float]] = []
    for cand in candidates:
        coord = candidate_coord(cand)
        heading = candidate_heading(cand)
        if coord is None or heading is None:
            continue
        delta = abs(angle_diff(heading, desired_heading_deg))
        direction_valid = delta <= max_heading_delta
        dist = haversine_m(coord, midpoint)
        recency_bonus = min(captured_ts(cand) / 1_000_000_000, 3)
        pano_bonus = 4 if cand.get("is_pano") else 0
        score = (1000 if direction_valid else 0) - delta * 8 - dist * 2 + recency_bonus + pano_bonus
        scored.append((score, cand, direction_valid, delta, dist))
    if not scored:
        return None
    score, cand, direction_valid, delta, dist = max(scored, key=lambda x: x[0])
    coord = candidate_coord(cand) or midpoint
    heading = candidate_heading(cand) or desired_heading_deg
    return {
        "id": f"photo_{cand.get('id', 'candidate')}",
        "source": "mapillary",
        "source_image_id": str(cand.get("id")),
        "image_url": cand.get("thumb_2048_url") or cand.get("thumb_1024_url") or cand.get("thumb_256_url"),
        "captured_at": cand.get("captured_at"),
        "lng": coord[0],
        "lat": coord[1],
        "compass_angle_deg": heading,
        "direction_valid": direction_valid,
        "direction_confidence": round(max(0, 1 - delta / max_heading_delta), 3) if direction_valid else 0,
        "distance_to_midpoint_m": round(dist, 2),
        "is_pano": bool(cand.get("is_pano")),
        "metadata": cand,
    }


def build_street_view_nodes(street_parts: list[dict[str, Any]], photos_by_part: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    photos_by_part = photos_by_part or {}
    nodes: list[dict[str, Any]] = []
    for i, part in enumerate(street_parts):
        active = photos_by_part.get(part["id"])
        node_id = f"street_view_node_{i:04d}"
        nodes.append(
            {
                "id": node_id,
                "street_part_id": part["id"],
                "active_photo_id": active.get("id") if active else None,
                "sequence_id": active.get("metadata", {}).get("sequence") if active else None,
                "sequence_index": i,
                "lng": part["midpoint"][0],
                "lat": part["midpoint"][1],
                "canonical_heading_deg": part["direction_bearing_deg"],
                "desired_orientation": part.get("desired_orientation", "road_right"),
                "prev_node_id": f"street_view_node_{i-1:04d}" if i else None,
                "next_node_id": f"street_view_node_{i+1:04d}" if i < len(street_parts) - 1 else None,
                "left_node_id": None,
                "right_node_id": None,
                "coverage_status": "active" if active else "missing",
            }
        )
    return nodes


def sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def jsonb_literal(value: Any) -> str:
    return sql_literal(json.dumps(value, separators=(",", ":"))) + "::jsonb"


def registry_to_supabase_seed_sql(registry: dict[str, Any]) -> str:
    """Export a street-view registry as idempotent Supabase seed SQL."""
    lines = [
        "-- Generated AccessTwin demo-corridor seed data.",
        "begin;",
    ]
    for part in registry.get("street_parts", []):
        mid = part["midpoint"]
        route_ids = ",".join(sql_literal(x) for x in part.get("route_segment_ids", []))
        lines.append(
            "insert into public.street_parts "
            "(external_id, route_segment_ids, geometry, midpoint_lng, midpoint_lat, direction_bearing_deg, desired_orientation, length_m, metrics) values ("
            f"{sql_literal(part['id'])}, array[{route_ids}]::text[], {jsonb_literal(part['geometry'])}, "
            f"{mid[0]}, {mid[1]}, {part['direction_bearing_deg']}, {sql_literal(part.get('desired_orientation', 'road_right'))}, "
            f"{part['length_m']}, {jsonb_literal(part.get('metrics', {}))}) "
            "on conflict (external_id) do update set "
            "route_segment_ids=excluded.route_segment_ids, geometry=excluded.geometry, midpoint_lng=excluded.midpoint_lng, "
            "midpoint_lat=excluded.midpoint_lat, direction_bearing_deg=excluded.direction_bearing_deg, "
            "desired_orientation=excluded.desired_orientation, length_m=excluded.length_m, metrics=excluded.metrics, updated_at=now();"
        )
    for node in registry.get("street_view_nodes", []):
        lines.append(
            "insert into public.street_view_nodes "
            "(external_id, street_part_id, sequence_id, sequence_index, lng, lat, canonical_heading_deg, desired_orientation, "
            "prev_node_external_id, next_node_external_id, left_node_external_id, right_node_external_id, coverage_status) values ("
            f"{sql_literal(node['id'])}, (select id from public.street_parts where external_id={sql_literal(node['street_part_id'])}), "
            f"{sql_literal(node.get('sequence_id'))}, {node.get('sequence_index') if node.get('sequence_index') is not None else 'null'}, "
            f"{node['lng']}, {node['lat']}, {node['canonical_heading_deg']}, {sql_literal(node.get('desired_orientation', 'road_right'))}, "
            f"{sql_literal(node.get('prev_node_id'))}, {sql_literal(node.get('next_node_id'))}, "
            f"{sql_literal(node.get('left_node_id'))}, {sql_literal(node.get('right_node_id'))}, {sql_literal(node.get('coverage_status', 'missing'))}) "
            "on conflict (external_id) do update set "
            "street_part_id=excluded.street_part_id, sequence_id=excluded.sequence_id, sequence_index=excluded.sequence_index, "
            "lng=excluded.lng, lat=excluded.lat, canonical_heading_deg=excluded.canonical_heading_deg, "
            "desired_orientation=excluded.desired_orientation, prev_node_external_id=excluded.prev_node_external_id, "
            "next_node_external_id=excluded.next_node_external_id, left_node_external_id=excluded.left_node_external_id, "
            "right_node_external_id=excluded.right_node_external_id, coverage_status=excluded.coverage_status, updated_at=now();"
        )
    lines.append("commit;")
    return "\n".join(lines) + "\n"


def build_registry(world: dict[str, Any], target_length_m: float = 10.0, max_parts: int | None = 30) -> dict[str, Any]:
    features = world.get("features", [])
    street_parts = group_segments_into_street_parts(features, target_length_m=target_length_m, max_parts=max_parts)
    nodes = build_street_view_nodes(street_parts)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_note": "Initial curated corridor graph. Photos are attached by Mapillary/crowd registry in the browser or Supabase layer.",
        "street_parts": street_parts,
        "street_photos": [],
        "street_view_nodes": nodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--target-length-m", type=float, default=10.0)
    parser.add_argument("--max-parts", type=int, default=30)
    parser.add_argument("--seed-sql", type=Path, default=None, help="Optional Supabase seed SQL output path")
    args = parser.parse_args()

    world = json.loads(args.world.read_text())
    registry = build_registry(world, target_length_m=args.target_length_m, max_parts=args.max_parts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, indent=2))
    if args.seed_sql:
        args.seed_sql.parent.mkdir(parents=True, exist_ok=True)
        args.seed_sql.write_text(registry_to_supabase_seed_sql(registry))
        print(f"wrote {args.seed_sql} seed SQL")
    print(f"wrote {args.out} with {len(registry['street_view_nodes'])} street-view nodes")


if __name__ == "__main__":
    main()
