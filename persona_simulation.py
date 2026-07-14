#!/usr/bin/env python3
"""Generate persona-based before/after accessibility simulation output.

This is the deterministic simulation layer for the AccessTwin / EquiRoute demo.
It consumes the current repo-root JSON artifacts:

- sim_output.json: graph edge export from the existing persona_agent notebook
- threejs_3d_roads.json: 3D OSM road/path mesh export from Clementi Mall scope

It outputs:

- sim_persona_before_after.json: frontend-ready before/after persona scores,
  bottlenecks, and per-edge visualisation fields.

Design principle:
The browser should render this JSON. Persona logic, edge scoring, and intervention
impact should live here, not be hardcoded in Three.js.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

Coord = tuple[float, float]  # (lng, lat)


# ----------------------------- geometry helpers -----------------------------


def haversine_m(a: Coord, b: Coord) -> float:
    """Approximate distance between lon/lat pairs in metres."""
    lon1, lat1 = a
    lon2, lat2 = b
    radius_m = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(h))


def midpoint(a: Coord, b: Coord) -> Coord:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def deg_distance(a: Coord, b: Coord) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_to_segment_deg(p: Coord, a: Coord, b: Coord) -> float:
    """Distance from p to segment ab in degrees. Good enough for local proximity tags."""
    px, py = p
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    denom = vx * vx + vy * vy
    if denom == 0:
        return deg_distance(p, a)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
    proj = (ax + t * vx, ay + t * vy)
    return deg_distance(p, proj)


def local_to_lnglat(point: list[float], anchor: list[float]) -> Coord:
    """Invert build_graph_clementi_mall.ipynb's local 3D coordinate transform."""
    x, _y, z = point
    center_lng, center_lat = anchor
    scale = 100_000
    lng = center_lng + x / scale
    lat = center_lat - z / scale
    return (lng, lat)


# ------------------------------- data models --------------------------------


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    description: str
    weights: dict[str, float]
    before_threshold: float
    after_threshold: float


PERSONAS: list[Persona] = [
    Persona(
        id="wheelchair_user",
        name="Wheelchair user",
        description="Avoids steps/kerbs, narrow spaces, steep or uneven paths, and high-detour routes.",
        weights={
            "step_risk": 40,
            "crossing_risk": 18,
            "traffic_proximity": 12,
            "long_segment": 9,
            "wayfinding_complexity": 7,
            "unsheltered_risk": 5,
        },
        before_threshold=28,
        after_threshold=34,
    ),
    Persona(
        id="senior_with_walker",
        name="Senior with walker",
        description="Sensitive to long walking distance, crossing time pressure, missing rest points, and uneven ground.",
        weights={
            "long_segment": 22,
            "crossing_risk": 18,
            "step_risk": 20,
            "traffic_proximity": 10,
            "wayfinding_complexity": 8,
            "unsheltered_risk": 8,
        },
        before_threshold=24,
        after_threshold=31,
    ),
    Persona(
        id="visually_impaired",
        name="Visually impaired commuter",
        description="Sensitive to ambiguous wayfinding, crossings, tactile/audio guidance gaps, and conflict with traffic/cycling flows.",
        weights={
            "wayfinding_complexity": 28,
            "crossing_risk": 24,
            "traffic_proximity": 14,
            "step_risk": 10,
            "long_segment": 5,
            "unsheltered_risk": 4,
        },
        before_threshold=24,
        after_threshold=30,
    ),
    Persona(
        id="pma_user",
        name="PMA / PMD user",
        description="Sensitive to narrow footpaths, bollards/obstructions, crowding, crossings, and routes that force road detours.",
        weights={
            "traffic_proximity": 20,
            "crossing_risk": 18,
            "step_risk": 22,
            "wayfinding_complexity": 7,
            "long_segment": 10,
            "unsheltered_risk": 5,
        },
        before_threshold=25,
        after_threshold=32,
    ),
]


INTERVENTIONS = {
    "accessibility_upgrade_bundle": {
        "name": "Accessibility upgrade bundle",
        "description": (
            "Simulates targeted improvements along the highest-risk Clementi Mall corridor: "
            "step-free kerb/ramp treatment, clearer route guidance, safer crossing support, "
            "and removal of temporary obstructions."
        ),
        "risk_reduction": {
            "step_risk": 0.75,
            "crossing_risk": 0.45,
            "wayfinding_complexity": 0.55,
            "traffic_proximity": 0.25,
            "long_segment": 0.15,
            "unsheltered_risk": 0.20,
        },
    }
}


# ----------------------------- feature tagging ------------------------------


def build_road_segments(threejs_payload: dict[str, Any]) -> list[dict[str, Any]]:
    anchor = threejs_payload["anchor_center"]
    segments: list[dict[str, Any]] = []
    for road in threejs_payload.get("mesh_roads", []):
        coords = [local_to_lnglat(pt, anchor) for pt in road.get("coordinates", [])]
        for a, b in zip(coords, coords[1:]):
            segments.append(
                {
                    "a": a,
                    "b": b,
                    "fclass": road.get("fclass", "unknown"),
                    "name": road.get("name", "Unnamed"),
                    "is_bridge": bool(road.get("is_bridge")),
                    "is_tunnel": bool(road.get("is_tunnel")),
                }
            )
    return segments


def proximity_to_fclass(point: Coord, road_segments: list[dict[str, Any]], classes: set[str]) -> float:
    best = float("inf")
    for seg in road_segments:
        if seg["fclass"] not in classes:
            continue
        d = point_to_segment_deg(point, seg["a"], seg["b"])
        if d < best:
            best = d
    return best


def infer_risks(edge: dict[str, Any], road_segments: list[dict[str, Any]]) -> dict[str, float]:
    a = tuple(edge["coords"][0])  # type: ignore[arg-type]
    b = tuple(edge["coords"][1])  # type: ignore[arg-type]
    mid = midpoint(a, b)
    distance = haversine_m(a, b)

    # Degree thresholds roughly map to metre-scale checks in Singapore.
    near_steps = proximity_to_fclass(mid, road_segments, {"steps"})
    near_primary = proximity_to_fclass(mid, road_segments, {"primary", "primary_link"})
    near_footway = proximity_to_fclass(mid, road_segments, {"footway", "pedestrian", "path"})
    near_cycleway = proximity_to_fclass(mid, road_segments, {"cycleway"})

    risks = {
        "step_risk": 1.0 if near_steps < 0.00008 else 0.0,
        "crossing_risk": 1.0 if near_primary < 0.00009 else 0.0,
        "traffic_proximity": max(0.0, 1.0 - near_primary / 0.00018) if near_primary != float("inf") else 0.0,
        "long_segment": min(1.0, max(0.0, (distance - 35) / 85)),
        "wayfinding_complexity": 0.0,
        "unsheltered_risk": 0.0,
    }

    # If an edge is not near an OSM footway/pedestrian line, treat it as harder to trust.
    if near_footway == float("inf") or near_footway > 0.00012:
        risks["wayfinding_complexity"] += 0.45

    # Cycleway/road interaction can confuse PMA and visually impaired users.
    if near_cycleway < 0.00010:
        risks["wayfinding_complexity"] += 0.25

    # Longer exposed segments are more likely to lack rest/shelter for this MVP.
    if distance > 45:
        risks["unsheltered_risk"] = min(1.0, (distance - 45) / 80)

    risks["wayfinding_complexity"] = min(1.0, risks["wayfinding_complexity"])
    risks["distance_m"] = distance
    return risks


# ------------------------------- scoring ------------------------------------


def persona_cost(risks: dict[str, float], persona: Persona) -> float:
    base = risks["distance_m"] / 20.0
    penalty = sum(risks.get(k, 0.0) * w for k, w in persona.weights.items())
    return round(base + penalty, 3)


def apply_intervention(risks: dict[str, float], intervention: dict[str, Any]) -> dict[str, float]:
    changed = dict(risks)
    for risk, reduction in intervention["risk_reduction"].items():
        changed[risk] = changed.get(risk, 0.0) * (1.0 - reduction)
    return changed


def score_from_costs(costs: Iterable[float]) -> int:
    values = list(costs)
    if not values:
        return 100
    # Higher average risk reduces confidence. Clamp for readable demo scores.
    avg = mean(values)
    score = round(100 - min(75, avg * 2.2))
    return max(0, min(100, score))


def top_bottlenecks(edges: list[dict[str, Any]], persona: Persona, limit: int = 5) -> list[dict[str, Any]]:
    sorted_edges = sorted(edges, key=lambda e: e["personas"][persona.id]["before_cost"], reverse=True)
    out = []
    for edge in sorted_edges[:limit]:
        p = edge["personas"][persona.id]
        active = [k for k, v in edge["risks"].items() if k != "distance_m" and v >= 0.35]
        out.append(
            {
                "edge_id": edge["id"],
                "coords": edge["coords"],
                "before_cost": p["before_cost"],
                "after_cost": p["after_cost"],
                "improvement": round(p["before_cost"] - p["after_cost"], 3),
                "risk_tags": active,
                "explanation": explain_bottleneck(active, persona),
            }
        )
    return out


def explain_bottleneck(tags: list[str], persona: Persona) -> str:
    if not tags:
        return f"This segment has elevated route cost for {persona.name.lower()} because of distance and uncertainty."
    human = {
        "step_risk": "possible step/kerb or level-change risk",
        "crossing_risk": "road-crossing or traffic interface risk",
        "traffic_proximity": "close interaction with major road traffic",
        "long_segment": "long exposed walking/rolling segment",
        "wayfinding_complexity": "unclear or less-trusted wayfinding path",
        "unsheltered_risk": "likely lack of rest or shelter along the segment",
    }
    issues = ", ".join(human.get(t, t) for t in tags)
    return f"For {persona.name.lower()}, this segment is high-risk due to {issues}."


# ------------------------------- main flow ----------------------------------


def generate(sim_output: Path, threejs_roads: Path, output: Path) -> dict[str, Any]:
    sim = json.loads(sim_output.read_text())
    roads = json.loads(threejs_roads.read_text())
    road_segments = build_road_segments(roads)
    intervention = INTERVENTIONS["accessibility_upgrade_bundle"]

    enriched_edges: list[dict[str, Any]] = []
    for idx, edge in enumerate(sim["edges"]):
        risks = infer_risks(edge, road_segments)
        after_risks = apply_intervention(risks, intervention)

        persona_payload: dict[str, Any] = {}
        for persona in PERSONAS:
            before_cost = persona_cost(risks, persona)
            after_cost = persona_cost(after_risks, persona)
            persona_payload[persona.id] = {
                "before_cost": before_cost,
                "after_cost": after_cost,
                "is_bottleneck_before": before_cost >= persona.before_threshold,
                "is_bottleneck_after": after_cost >= persona.after_threshold,
            }

        enriched_edges.append(
            {
                "id": f"edge_{idx:05d}",
                "coords": edge["coords"],
                "distance_m": round(risks["distance_m"], 2),
                "risks": {k: round(v, 3) for k, v in risks.items()},
                "after_risks": {k: round(v, 3) for k, v in after_risks.items()},
                "personas": persona_payload,
                # Keep backwards-compatible colour hook for current index_datamall.html.
                "isHighCost": any(p["is_bottleneck_before"] for p in persona_payload.values()),
            }
        )

    persona_summaries: dict[str, Any] = {}
    for persona in PERSONAS:
        before_costs = [e["personas"][persona.id]["before_cost"] for e in enriched_edges]
        after_costs = [e["personas"][persona.id]["after_cost"] for e in enriched_edges]
        before_bottlenecks = sum(e["personas"][persona.id]["is_bottleneck_before"] for e in enriched_edges)
        after_bottlenecks = sum(e["personas"][persona.id]["is_bottleneck_after"] for e in enriched_edges)
        persona_summaries[persona.id] = {
            "name": persona.name,
            "description": persona.description,
            "before_score": score_from_costs(before_costs),
            "after_score": score_from_costs(after_costs),
            "bottleneck_edges_before": before_bottlenecks,
            "bottleneck_edges_after": after_bottlenecks,
            "top_bottlenecks": top_bottlenecks(enriched_edges, persona),
        }
        persona_summaries[persona.id]["score_delta"] = (
            persona_summaries[persona.id]["after_score"]
            - persona_summaries[persona.id]["before_score"]
        )

    output_payload = {
        "project": "AccessTwin / EquiRoute Clementi Mall persona simulation",
        "route": {
            "name": "Clementi MRT / Clementi Mall accessibility corridor",
            "start": sim.get("start"),
            "end": sim.get("end"),
            "scope": "Clementi Mall / Clementi MRT local world model",
        },
        "intervention": intervention,
        "personas": persona_summaries,
        "edges": enriched_edges,
        "source_files": {
            "sim_output": str(sim_output),
            "threejs_roads": str(threejs_roads),
        },
    }
    output.write_text(json.dumps(output_payload, indent=2))
    return output_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim-output", default="sim_output.json", type=Path)
    parser.add_argument("--threejs-roads", default="threejs_3d_roads.json", type=Path)
    parser.add_argument("--output", default="sim_persona_before_after.json", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = generate(args.sim_output, args.threejs_roads, args.output)
    print(f"wrote {args.output}")
    print(f"edges: {len(payload['edges'])}")
    for persona_id, summary in payload["personas"].items():
        print(
            f"{persona_id}: {summary['before_score']} -> {summary['after_score']} "
            f"(+{summary['score_delta']}), bottlenecks "
            f"{summary['bottleneck_edges_before']} -> {summary['bottleneck_edges_after']}"
        )


if __name__ == "__main__":
    main()
