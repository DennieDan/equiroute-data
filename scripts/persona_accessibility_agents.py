#!/usr/bin/env python3
"""Simulate disability persona agents over the AccessTwin street-part map.

The frontend works at public ~25 m street-part granularity, while
`accessibility_world.geojson` keeps hidden ~5 m measurement segments. This script
aggregates the 5 m segment persona scores/blockers into street-part journeys and
recommends concrete improvements for each persona.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORLD = ROOT / "accessibility_world.geojson"
DEFAULT_REGISTRY = ROOT / "data/street_view_registry.json"
DEFAULT_OUTPUT = ROOT / "data/persona_agent_travel_simulation.json"

PERSONA_ORDER = [
    "wheelchair_user",
    "senior_with_walker",
    "visually_impaired",
    "pma_user",
]

BLOCKER_LABELS = {
    "clear_width": "narrow clear width",
    "running_slope": "steep running slope",
    "cross_slope": "side slope / camber",
    "surface_roughness": "rough or uneven surface",
    "vertical_change": "kerb / level change",
    "obstructions": "bollards or obstructions",
    "shelter": "missing shelter",
    "rest_distance": "long gap without rest point",
    "crossing_safety": "crossing safety / kerb ramp gap",
    "tactile_guidance": "missing tactile guidance",
    "wayfinding": "unclear wayfinding",
    "contrast": "low visual contrast",
}

IMPROVEMENT_BY_BLOCKER = {
    "clear_width": "widen this footpath section or remove pinch-point obstructions",
    "running_slope": "smooth the gradient or provide a compliant ramp alternative",
    "cross_slope": "regrade the pavement to reduce side slope",
    "surface_roughness": "resurface the path with stable, firm, slip-resistant material",
    "vertical_change": "add/repair kerb ramp treatment and flush transitions",
    "obstructions": "relocate bollards/furniture outside the accessible clear path",
    "shelter": "extend covered linkway or add sheltered rest points",
    "rest_distance": "add rest point / bench zone near this segment",
    "crossing_safety": "add kerb ramp, tactile cues, and clearer crossing priority",
    "tactile_guidance": "continue tactile paving across the decision point/crossing",
    "wayfinding": "add high-contrast directional cues and clearer path continuity",
    "contrast": "improve colour contrast and edge definition",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def segment_lookup(world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for feature in world.get("features", []):
        props = feature.get("properties", {})
        if props.get("kind") == "route_segment":
            out[props["id"]] = feature
    return out


def aggregate_part(part: dict[str, Any], segments: dict[str, dict[str, Any]], personas: dict[str, Any]) -> dict[str, Any]:
    segs = [segments[sid] for sid in part.get("route_segment_ids", []) if sid in segments]
    persona_payload: dict[str, Any] = {}
    part_metrics = part.get("metrics", {})
    length_m = float(part.get("length_m") or 0)

    for persona_id in PERSONA_ORDER:
        scores = []
        blockers: Counter[str] = Counter()
        worst_segment = None
        worst_score = 101
        for seg in segs:
            props = seg["properties"]
            p = props.get("personas", {}).get(persona_id, {})
            score = int(p.get("score", props.get("overall_accessibility_score", 0)))
            scores.append(score)
            for blocker in p.get("blockers", []):
                blockers[blocker] += 1
            if score < worst_score:
                worst_score = score
                worst_segment = props.get("id")
        avg_score = round(mean(scores)) if scores else int(part_metrics.get("overall_accessibility_score", 0) or 0)
        top_blockers = [b for b, _ in blockers.most_common(4)]
        improvement = top_blockers[0] if top_blockers else ""
        persona_payload[persona_id] = {
            "label": personas.get(persona_id, {}).get("label", persona_id.replace("_", " ").title()),
            "score": avg_score,
            "passable": avg_score >= 67 and not any(b in top_blockers for b in ("vertical_change", "clear_width")) ,
            "status": "passable" if avg_score >= 67 else "needs_improvement",
            "blockers": top_blockers,
            "blocker_labels": [BLOCKER_LABELS.get(b, b.replace("_", " ")) for b in top_blockers],
            "recommended_improvement": IMPROVEMENT_BY_BLOCKER.get(improvement, "keep current path; monitor with field audit"),
            "worst_segment_id": worst_segment,
        }

    worst_persona = min(persona_payload, key=lambda pid: persona_payload[pid]["score"])
    blocker_counts = Counter(b for p in persona_payload.values() for b in p["blockers"])
    top_blocker = blocker_counts.most_common(1)[0][0] if blocker_counts else ""
    return {
        "street_part_id": part["id"],
        "street_id": part.get("street_id"),
        "name": part.get("name") or part["id"],
        "route_segment_ids": part.get("route_segment_ids", []),
        "midpoint": part.get("midpoint"),
        "length_m": round(length_m, 2),
        "overall_score": round(mean([p["score"] for p in persona_payload.values()])),
        "worst_persona": worst_persona,
        "top_blocker": top_blocker,
        "recommended_improvement": IMPROVEMENT_BY_BLOCKER.get(top_blocker, "keep current path; verify with field audit"),
        "personas": persona_payload,
    }


def build_simulation(world: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    segments = segment_lookup(world)
    personas = world.get("personas", {})
    parts = [aggregate_part(part, segments, personas) for part in registry.get("street_parts", [])]
    persona_summaries: dict[str, Any] = {}
    for persona_id in PERSONA_ORDER:
        entries = [p for p in parts if persona_id in p["personas"]]
        scores = [p["personas"][persona_id]["score"] for p in entries]
        blockers = Counter(b for p in entries for b in p["personas"][persona_id]["blockers"])
        bottlenecks = sorted(entries, key=lambda p: p["personas"][persona_id]["score"])[:5]
        persona_summaries[persona_id] = {
            "label": personas.get(persona_id, {}).get("label", persona_id.replace("_", " ").title()),
            "average_score": round(mean(scores)) if scores else 0,
            "passable_parts": sum(1 for p in entries if p["personas"][persona_id]["passable"]),
            "total_parts": len(entries),
            "top_blockers": [
                {"blocker": b, "label": BLOCKER_LABELS.get(b, b), "count": c, "improvement": IMPROVEMENT_BY_BLOCKER.get(b, "field audit")}
                for b, c in blockers.most_common(5)
            ],
            "priority_street_parts": [
                {
                    "street_part_id": p["street_part_id"],
                    "street_id": p["street_id"],
                    "score": p["personas"][persona_id]["score"],
                    "blockers": p["personas"][persona_id]["blocker_labels"],
                    "recommended_improvement": p["personas"][persona_id]["recommended_improvement"],
                }
                for p in bottlenecks
            ],
        }
    return {
        "project": "AccessTwin Clementi persona-agent travel simulation",
        "unit": "25m street_part aggregated from hidden 5m measurement segments",
        "method": "deterministic proxy scoring from accessibility_world.geojson persona segment scores",
        "personas": persona_summaries,
        "street_parts": parts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--street-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_simulation(load_json(args.world), load_json(args.street_registry))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    print(f"wrote {args.output}")
    print(f"street_parts: {len(payload['street_parts'])}")
    for pid, summary in payload["personas"].items():
        print(f"{pid}: {summary['average_score']}/100, passable {summary['passable_parts']}/{summary['total_parts']}")


if __name__ == "__main__":
    main()
