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
import os
import time
import urllib.parse
import urllib.request
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


def build_streets(street_parts: list[dict[str, Any]], turn_threshold_deg: float = 55.0) -> list[dict[str, Any]]:
    """Assign each street part to a parent street.

    A street is a contiguous run of street parts with broadly consistent bearing.
    This is intentionally simple for the hack MVP; later we can replace it with
    OSM road names/way IDs once we ingest full road-centerline data.
    """
    streets: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_part: dict[str, Any] | None = None

    def new_street(part: dict[str, Any]) -> dict[str, Any]:
        street = {
            "id": f"street_{len(streets):04d}",
            "name": f"Demo Street {len(streets) + 1}",
            "source": "generated_bearing_runs",
            "desired_orientation": part.get("desired_orientation", "road_right"),
            "street_part_ids": [],
            "geometry": {"type": "LineString", "coordinates": []},
            "metrics": {},
        }
        streets.append(street)
        return street

    for part in street_parts:
        if current is None:
            current = new_street(part)
        elif previous_part is not None and abs(angle_diff(part["direction_bearing_deg"], previous_part["direction_bearing_deg"])) > turn_threshold_deg:
            current = new_street(part)

        part["street_id"] = current["id"]
        current["street_part_ids"].append(part["id"])
        coords = part.get("geometry", {}).get("coordinates", [])
        if not current["geometry"]["coordinates"]:
            current["geometry"]["coordinates"].extend(coords)
        else:
            current["geometry"]["coordinates"].extend(coords[1:] if coords and current["geometry"]["coordinates"][-1] == coords[0] else coords)
        previous_part = part

    for street in streets:
        coords = street["geometry"]["coordinates"]
        if coords:
            street["midpoint"] = midpoint(coords)
            street["direction_bearing_deg"] = round(bearing_deg(coords[0], coords[-1]), 2)
            street["length_m"] = round(sum(haversine_m(a, b) for a, b in zip(coords, coords[1:])), 2)
            street["metrics"] = {"street_part_count": len(street["street_part_ids"])}
    return streets


MAPILLARY_FIELDS = ",".join(
    [
        "id",
        "is_pano",
        "thumb_2048_url",
        "thumb_1024_url",
        "thumb_256_url",
        "geometry",
        "computed_geometry",
        "compass_angle",
        "computed_compass_angle",
        "captured_at",
        "sequence",
    ]
)


def mapillary_images_url(lng: float, lat: float, token: str, radius_m: int = 45, limit: int = 12) -> str:
    params = {
        "fields": MAPILLARY_FIELDS,
        "lat": f"{lat:.7f}",
        "lng": f"{lng:.7f}",
        "radius": str(radius_m),
        "limit": str(limit),
        "access_token": token,
    }
    return "https://graph.mapillary.com/images?" + urllib.parse.urlencode(params)


def fetch_mapillary_images(
    lng: float,
    lat: float,
    token: str,
    radius_m: int = 45,
    limit: int = 12,
    timeout_s: int = 20,
) -> list[dict[str, Any]]:
    """Fetch Mapillary image candidates for one street-part midpoint.

    The caller is responsible for providing a token; this function never logs or
    stores the token, and the token is not included in returned metadata.
    """
    url = mapillary_images_url(lng, lat, token, radius_m=radius_m, limit=limit)
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    for row in rows:
        row.setdefault("source", "mapillary")
    return rows


def harvest_mapillary_candidates(
    street_parts: list[dict[str, Any]],
    token: str,
    radius_m: int = 45,
    limit_per_part: int = 12,
    sleep_s: float = 0.12,
) -> dict[str, list[dict[str, Any]]]:
    """Harvest candidate photos keyed by street_part external id."""
    candidates_by_part: dict[str, list[dict[str, Any]]] = {}
    seen_by_part: dict[str, set[str]] = {}
    for i, part in enumerate(street_parts, start=1):
        mid = part.get("midpoint") or [None, None]
        lng, lat = mid[0], mid[1]
        if lng is None or lat is None:
            continue
        rows = fetch_mapillary_images(
            float(lng),
            float(lat),
            token=token,
            radius_m=radius_m,
            limit=limit_per_part,
        )
        seen = seen_by_part.setdefault(part["id"], set())
        clean_rows = []
        for row in rows:
            image_id = str(row.get("id") or "")
            if not image_id or image_id in seen:
                continue
            seen.add(image_id)
            clean_rows.append(row)
        candidates_by_part[part["id"]] = clean_rows
        if sleep_s and i < len(street_parts):
            time.sleep(sleep_s)
    return candidates_by_part


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


def desired_photo_headings(part_heading_deg: float) -> list[dict[str, Any]]:
    """Return candidate camera headings for both pavement sides of a two-way road.

    `road_right` preserves the original direction. `road_left_pavement_right`
    uses the opposite compass heading so a two-way road with pavement on the
    other side can still show the pedestrian path on the right of the image.
    """
    base = float(part_heading_deg) % 360
    return [
        {"heading_deg": base, "orientation": "road_right", "heading_role": "canonical"},
        {"heading_deg": (base + 180) % 360, "orientation": "road_left_pavement_right", "heading_role": "opposite"},
    ]


def choose_best_photo(
    candidates: list[dict[str, Any]],
    midpoint: list[float],
    desired_heading_deg: float,
    max_heading_delta: float = 35,
    allow_opposite_heading: bool = True,
) -> dict[str, Any] | None:
    """Choose best candidate by direction first, then distance/recency/pano.

    For two-way roads we evaluate both headings: the canonical road-on-right
    heading and the opposite heading where the road may be left and pavement
    stays visible on the right.
    """
    heading_options = desired_photo_headings(desired_heading_deg) if allow_opposite_heading else [desired_photo_headings(desired_heading_deg)[0]]
    scored: list[tuple[float, dict[str, Any], bool, float, float, dict[str, Any]]] = []
    for cand in candidates:
        coord = candidate_coord(cand)
        heading = candidate_heading(cand)
        if coord is None or heading is None:
            continue
        best_option = min(heading_options, key=lambda opt: abs(angle_diff(heading, opt["heading_deg"])))
        delta = abs(angle_diff(heading, best_option["heading_deg"]))
        direction_valid = delta <= max_heading_delta
        dist = haversine_m(coord, midpoint)
        recency_bonus = min(captured_ts(cand) / 1_000_000_000, 3)
        pano_bonus = 4 if cand.get("is_pano") else 0
        opposite_penalty = 8 if best_option["heading_role"] == "opposite" else 0
        score = (1000 if direction_valid else 0) - delta * 8 - dist * 2 + recency_bonus + pano_bonus - opposite_penalty
        scored.append((score, cand, direction_valid, delta, dist, best_option))
    if not scored:
        return None
    score, cand, direction_valid, delta, dist, best_option = max(scored, key=lambda x: x[0])
    coord = candidate_coord(cand) or midpoint
    heading = candidate_heading(cand) or desired_heading_deg
    metadata = dict(cand)
    metadata["selected_heading_option"] = best_option
    return {
        "id": f"photo_{cand.get('id', 'candidate')}",
        "source": "mapillary",
        "source_image_id": str(cand.get("id")),
        "image_url": cand.get("thumb_2048_url") or cand.get("thumb_1024_url") or cand.get("thumb_256_url"),
        "captured_at": cand.get("captured_at"),
        "lng": coord[0],
        "lat": coord[1],
        "compass_angle_deg": heading,
        "matched_heading_deg": best_option["heading_deg"],
        "heading_role": best_option["heading_role"],
        "desired_orientation": best_option["orientation"],
        "direction_valid": direction_valid,
        "direction_confidence": round(max(0, 1 - delta / max_heading_delta), 3) if direction_valid else 0,
        "distance_to_midpoint_m": round(dist, 2),
        "is_pano": bool(cand.get("is_pano")),
        "metadata": metadata,
    }


def photo_external_id(photo: dict[str, Any]) -> str:
    if photo.get("external_id"):
        return str(photo["external_id"])
    source = photo.get("source", "photo")
    raw = photo.get("source_image_id") or photo.get("id") or "unknown"
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(raw))
    return f"photo_{source}_{safe}"


def attach_active_photos(
    street_parts: list[dict[str, Any]],
    candidates_by_part: dict[str, list[dict[str, Any]]],
    max_heading_delta: float = 35,
) -> list[dict[str, Any]]:
    """Choose one active photo per street part from Mapillary/crowd candidates.

    Comments and feedback stay attached to street_part_id; photos can be replaced
    over time while preserving discussion history.
    """
    photos: list[dict[str, Any]] = []
    for part in street_parts:
        candidates = candidates_by_part.get(part["id"], [])
        chosen = choose_best_photo(
            candidates,
            midpoint=part["midpoint"],
            desired_heading_deg=part["direction_bearing_deg"],
            max_heading_delta=max_heading_delta,
        )
        if not chosen:
            continue
        chosen["external_id"] = photo_external_id(chosen)
        chosen["id"] = chosen["external_id"]
        chosen["street_part_id"] = part["id"]
        chosen["street_id"] = part.get("street_id")
        chosen["is_active"] = True
        chosen["validation_status"] = "direction_valid" if chosen.get("direction_valid") else "needs_review"
        chosen["selected_reason"] = "best_direction_distance_recency_candidate"
        chosen["replaces_photo_id"] = None
        photos.append(chosen)
    return photos


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
                "street_id": part.get("street_id"),
                "active_photo_id": active.get("id") if active else None,
                "sequence_id": active.get("metadata", {}).get("sequence") if active else None,
                "sequence_index": i,
                "lng": part["midpoint"][0],
                "lat": part["midpoint"][1],
                "canonical_heading_deg": part["direction_bearing_deg"],
                "desired_orientation": part.get("desired_orientation", "road_right"),
                "prev_node_id": f"street_view_node_{i-1:04d}" if i and street_parts[i - 1].get("street_id") == part.get("street_id") else None,
                "next_node_id": f"street_view_node_{i+1:04d}" if i < len(street_parts) - 1 and street_parts[i + 1].get("street_id") == part.get("street_id") else None,
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
    for street in registry.get("streets", []):
        mid = street.get("midpoint", [None, None])
        lines.append(
            "insert into public.streets "
            "(external_id, name, geometry, midpoint_lng, midpoint_lat, direction_bearing_deg, desired_orientation, length_m, metrics) values ("
            f"{sql_literal(street['id'])}, {sql_literal(street.get('name'))}, {jsonb_literal(street['geometry'])}, "
            f"{mid[0]}, {mid[1]}, {street.get('direction_bearing_deg', 0)}, {sql_literal(street.get('desired_orientation', 'road_right'))}, "
            f"{street.get('length_m', 0)}, {jsonb_literal(street.get('metrics', {}))}) "
            "on conflict (external_id) do update set "
            "name=excluded.name, geometry=excluded.geometry, midpoint_lng=excluded.midpoint_lng, midpoint_lat=excluded.midpoint_lat, "
            "direction_bearing_deg=excluded.direction_bearing_deg, desired_orientation=excluded.desired_orientation, "
            "length_m=excluded.length_m, metrics=excluded.metrics, updated_at=now();"
        )
    for part in registry.get("street_parts", []):
        mid = part["midpoint"]
        route_ids = ",".join(sql_literal(x) for x in part.get("route_segment_ids", []))
        lines.append(
            "insert into public.street_parts "
            "(external_id, street_id, route_segment_ids, geometry, midpoint_lng, midpoint_lat, direction_bearing_deg, desired_orientation, length_m, metrics) values ("
            f"{sql_literal(part['id'])}, (select id from public.streets where external_id={sql_literal(part.get('street_id'))}), array[{route_ids}]::text[], {jsonb_literal(part['geometry'])}, "
            f"{mid[0]}, {mid[1]}, {part['direction_bearing_deg']}, {sql_literal(part.get('desired_orientation', 'road_right'))}, "
            f"{part['length_m']}, {jsonb_literal(part.get('metrics', {}))}) "
            "on conflict (external_id) do update set "
            "street_id=excluded.street_id, route_segment_ids=excluded.route_segment_ids, geometry=excluded.geometry, midpoint_lng=excluded.midpoint_lng, "
            "midpoint_lat=excluded.midpoint_lat, direction_bearing_deg=excluded.direction_bearing_deg, "
            "desired_orientation=excluded.desired_orientation, length_m=excluded.length_m, metrics=excluded.metrics, updated_at=now();"
        )
    for photo in registry.get("street_photos", []):
        lines.append(
            "insert into public.street_photos "
            "(external_id, street_part_id, source, source_image_id, image_url, captured_at, lng, lat, compass_angle_deg, "
            "direction_valid, direction_confidence, is_pano, is_active, validation_status, selected_reason, metadata) values ("
            f"{sql_literal(photo['external_id'])}, (select id from public.street_parts where external_id={sql_literal(photo['street_part_id'])}), "
            f"{sql_literal(photo.get('source', 'mapillary'))}, {sql_literal(photo.get('source_image_id'))}, {sql_literal(photo.get('image_url'))}, "
            f"{sql_literal(photo.get('captured_at'))}, {photo.get('lng')}, {photo.get('lat')}, {photo.get('compass_angle_deg')}, "
            f"{str(bool(photo.get('direction_valid'))).lower()}, {photo.get('direction_confidence') if photo.get('direction_confidence') is not None else 'null'}, "
            f"{str(bool(photo.get('is_pano'))).lower()}, {str(bool(photo.get('is_active'))).lower()}, "
            f"{sql_literal(photo.get('validation_status', 'needs_review'))}, {sql_literal(photo.get('selected_reason'))}, {jsonb_literal(photo.get('metadata', {}))}) "
            "on conflict (external_id) do update set "
            "street_part_id=excluded.street_part_id, source=excluded.source, source_image_id=excluded.source_image_id, image_url=excluded.image_url, "
            "captured_at=excluded.captured_at, lng=excluded.lng, lat=excluded.lat, compass_angle_deg=excluded.compass_angle_deg, "
            "direction_valid=excluded.direction_valid, direction_confidence=excluded.direction_confidence, is_pano=excluded.is_pano, "
            "is_active=excluded.is_active, validation_status=excluded.validation_status, selected_reason=excluded.selected_reason, "
            "metadata=excluded.metadata;"
        )
    for node in registry.get("street_view_nodes", []):
        lines.append(
            "insert into public.street_view_nodes "
            "(external_id, street_part_id, street_id, sequence_id, sequence_index, lng, lat, canonical_heading_deg, desired_orientation, "
            "prev_node_external_id, next_node_external_id, left_node_external_id, right_node_external_id, coverage_status) values ("
            f"{sql_literal(node['id'])}, (select id from public.street_parts where external_id={sql_literal(node['street_part_id'])}), "
            f"(select id from public.streets where external_id={sql_literal(node.get('street_id'))}), "
            f"{sql_literal(node.get('sequence_id'))}, {node.get('sequence_index') if node.get('sequence_index') is not None else 'null'}, "
            f"{node['lng']}, {node['lat']}, {node['canonical_heading_deg']}, {sql_literal(node.get('desired_orientation', 'road_right'))}, "
            f"{sql_literal(node.get('prev_node_id'))}, {sql_literal(node.get('next_node_id'))}, "
            f"{sql_literal(node.get('left_node_id'))}, {sql_literal(node.get('right_node_id'))}, {sql_literal(node.get('coverage_status', 'missing'))}) "
            "on conflict (external_id) do update set "
            "street_part_id=excluded.street_part_id, street_id=excluded.street_id, sequence_id=excluded.sequence_id, sequence_index=excluded.sequence_index, "
            "lng=excluded.lng, lat=excluded.lat, canonical_heading_deg=excluded.canonical_heading_deg, "
            "desired_orientation=excluded.desired_orientation, prev_node_external_id=excluded.prev_node_external_id, "
            "next_node_external_id=excluded.next_node_external_id, left_node_external_id=excluded.left_node_external_id, "
            "right_node_external_id=excluded.right_node_external_id, coverage_status=excluded.coverage_status, updated_at=now();"
        )
    for photo in registry.get("street_photos", []):
        lines.append(
            "update public.street_photos set street_view_node_id = "
            f"(select id from public.street_view_nodes where street_part_id=(select id from public.street_parts where external_id={sql_literal(photo['street_part_id'])}) limit 1) "
            f"where external_id={sql_literal(photo['external_id'])};"
        )
        lines.append(
            "update public.street_parts set active_photo_id = "
            f"(select id from public.street_photos where external_id={sql_literal(photo['external_id'])}) "
            f"where external_id={sql_literal(photo['street_part_id'])} and {str(bool(photo.get('is_active'))).lower()};"
        )
        lines.append(
            "update public.street_view_nodes set active_photo_id = "
            f"(select id from public.street_photos where external_id={sql_literal(photo['external_id'])}), coverage_status='active' "
            f"where street_part_id=(select id from public.street_parts where external_id={sql_literal(photo['street_part_id'])}) and {str(bool(photo.get('is_active'))).lower()};"
        )
    lines.append("commit;")
    return "\n".join(lines) + "\n"


def build_registry(
    world: dict[str, Any],
    target_length_m: float = 10.0,
    max_parts: int | None = 30,
    photo_candidates_by_part: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    features = world.get("features", [])
    street_parts = group_segments_into_street_parts(features, target_length_m=target_length_m, max_parts=max_parts)
    streets = build_streets(street_parts)
    street_photos = attach_active_photos(street_parts, photo_candidates_by_part or {})
    nodes = build_street_view_nodes(street_parts, {p["street_part_id"]: p for p in street_photos})
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_note": "Initial curated corridor graph. Streets contain street parts; photos attach to street parts/nodes through Mapillary/crowd registry.",
        "streets": streets,
        "street_parts": street_parts,
        "street_photos": street_photos,
        "street_view_nodes": nodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--target-length-m", type=float, default=10.0)
    parser.add_argument("--max-parts", type=int, default=30)
    parser.add_argument("--photo-candidates", type=Path, default=None, help="Optional JSON mapping street_part_id -> Mapillary/crowd candidate photos")
    parser.add_argument("--harvest-mapillary", action="store_true", help="Fetch Mapillary candidates for generated street parts before selecting active photos")
    parser.add_argument("--mapillary-token-env", default="MAPILLARY_TOKEN", help="Environment variable containing the Mapillary token")
    parser.add_argument("--mapillary-radius-m", type=int, default=45)
    parser.add_argument("--mapillary-limit-per-part", type=int, default=12)
    parser.add_argument("--candidate-out", type=Path, default=None, help="Optional JSON output path for raw candidates keyed by street_part id")
    parser.add_argument("--seed-sql", type=Path, default=None, help="Optional Supabase seed SQL output path")
    args = parser.parse_args()

    world = json.loads(args.world.read_text())
    photo_candidates = json.loads(args.photo_candidates.read_text()) if args.photo_candidates else None
    if args.harvest_mapillary:
        token = os.environ.get(args.mapillary_token_env, "").strip()
        if not token:
            raise SystemExit(f"Missing Mapillary token env var: {args.mapillary_token_env}")
        preview_parts = group_segments_into_street_parts(
            world.get("features", []),
            target_length_m=args.target_length_m,
            max_parts=args.max_parts,
        )
        photo_candidates = harvest_mapillary_candidates(
            preview_parts,
            token=token,
            radius_m=args.mapillary_radius_m,
            limit_per_part=args.mapillary_limit_per_part,
        )
        if args.candidate_out:
            args.candidate_out.parent.mkdir(parents=True, exist_ok=True)
            args.candidate_out.write_text(json.dumps(photo_candidates, indent=2))
            total_candidates = sum(len(v) for v in photo_candidates.values())
            print(f"wrote {args.candidate_out} with {total_candidates} raw Mapillary candidates")
    registry = build_registry(
        world,
        target_length_m=args.target_length_m,
        max_parts=args.max_parts,
        photo_candidates_by_part=photo_candidates,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, indent=2))
    if args.seed_sql:
        args.seed_sql.parent.mkdir(parents=True, exist_ok=True)
        args.seed_sql.write_text(registry_to_supabase_seed_sql(registry))
        print(f"wrote {args.seed_sql} seed SQL")
    print(f"wrote {args.out} with {len(registry['street_view_nodes'])} street-view nodes")


if __name__ == "__main__":
    main()
