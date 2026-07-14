#!/usr/bin/env python3
"""Apply a PERS-inspired pedestrian accessibility scoring layer.

There is no open, globally binding street-accessibility benchmark for our exact
hackathon data model. The closest renowned practice is PERS, the Pedestrian
Environment Review System developed by TRL/TfL. PERS audits pedestrian links,
crossings, routes, public transport waiting areas, public spaces, and interchange
spaces with weighted criteria and a -3..+3 score scale.

This script maps our synthetic risk fields onto PERS-like link/crossing
criteria, keeps persona-specific weights, and writes frontend-ready 0..100
before/after scores. It is intentionally deterministic and transparent so we can
explain it to judges as a PERS-inspired MVP, not a certified PERS audit.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

INPUT = Path("sim_persona_before_after.json")
OUTPUT = Path("sim_persona_before_after.json")

SCORING_METHODOLOGY = {
    "name": "PERS-inspired weighted pedestrian accessibility score",
    "benchmark_basis": "Pedestrian Environment Review System (PERS), developed by TRL/TfL, commonly used for pedestrian environment audits.",
    "note": "This is not a certified PERS field audit. It adapts PERS-style weighted link/crossing criteria to available OSM/LTA-derived proxy features for the Tech4City prototype.",
    "scale": "0-100, where 100 is best. Risk proxies are converted to a PERS-like -3..+3 criterion score, then weighted by persona needs.",
    "pers_reference_scale": {"very_poor": -3, "average": 0, "very_good": 3},
    "criteria_mapping": {
        "step_risk": "Dropped kerbs / steps and ramps / wheelchair accessibility",
        "crossing_risk": "Crossing quality, desire line, crossing capacity and suitability",
        "traffic_proximity": "Separation from traffic and user conflict",
        "long_segment": "Effective route burden, rest opportunity and distance stress",
        "wayfinding_complexity": "Legibility, tactile/visual information and consistency",
        "unsheltered_risk": "Quality of environment, comfort and weather exposure",
    },
    "rag_thresholds": {
        "green": ">= 67",
        "amber": "45-66",
        "red": "< 45",
    },
}

PERSONA_WEIGHTS = {
    "wheelchair_user": {
        "step_risk": 0.34,
        "crossing_risk": 0.20,
        "traffic_proximity": 0.14,
        "long_segment": 0.12,
        "wayfinding_complexity": 0.12,
        "unsheltered_risk": 0.08,
    },
    "senior_with_walker": {
        "long_segment": 0.26,
        "step_risk": 0.22,
        "crossing_risk": 0.20,
        "traffic_proximity": 0.10,
        "wayfinding_complexity": 0.10,
        "unsheltered_risk": 0.12,
    },
    "visually_impaired": {
        "wayfinding_complexity": 0.34,
        "crossing_risk": 0.25,
        "traffic_proximity": 0.16,
        "step_risk": 0.11,
        "long_segment": 0.06,
        "unsheltered_risk": 0.08,
    },
    "pma_user": {
        "traffic_proximity": 0.24,
        "crossing_risk": 0.22,
        "step_risk": 0.23,
        "long_segment": 0.13,
        "wayfinding_complexity": 0.10,
        "unsheltered_risk": 0.08,
    },
}


def risk_to_pers_score(risk: float) -> float:
    """Map risk 0..1 to PERS-like +3..-3."""
    risk = max(0.0, min(1.0, float(risk)))
    return 3.0 - 6.0 * risk


def pers_to_percent(weighted_pers_score: float) -> int:
    """Map PERS -3..+3 to 0..100."""
    return round(max(0.0, min(100.0, (weighted_pers_score + 3.0) / 6.0 * 100.0)))


def edge_percent(risks: dict, persona_id: str) -> int:
    weights = PERSONA_WEIGHTS[persona_id]
    weighted = sum(risk_to_pers_score(risks.get(k, 0.0)) * w for k, w in weights.items())
    return pers_to_percent(weighted)


def risk_tags(risks: dict) -> list[str]:
    return [k for k, v in risks.items() if k != "distance_m" and float(v) >= 0.35]


def main() -> None:
    payload = json.loads(INPUT.read_text())
    payload["scoring_methodology"] = SCORING_METHODOLOGY

    for edge in payload["edges"]:
        for persona_id, persona_edge in edge["personas"].items():
            before = edge_percent(edge["risks"], persona_id)
            after = edge_percent(edge["after_risks"], persona_id)
            persona_edge["pers_before_score"] = before
            persona_edge["pers_after_score"] = after
            persona_edge["pers_delta"] = after - before
            # Keep cost fields for backwards compatibility, but use PERS-like
            # RAG thresholds for the current frontend/summary.
            persona_edge["is_bottleneck_before"] = before < 45
            persona_edge["is_bottleneck_after"] = after < 45

        edge["pers_risk_tags"] = risk_tags(edge["risks"])

    for persona_id, persona in payload["personas"].items():
        before_scores = [e["personas"][persona_id]["pers_before_score"] for e in payload["edges"]]
        after_scores = [e["personas"][persona_id]["pers_after_score"] for e in payload["edges"]]
        before_bottlenecks = sum(e["personas"][persona_id]["is_bottleneck_before"] for e in payload["edges"])
        after_bottlenecks = sum(e["personas"][persona_id]["is_bottleneck_after"] for e in payload["edges"])
        persona["before_score"] = round(mean(before_scores))
        persona["after_score"] = round(mean(after_scores))
        persona["score_delta"] = persona["after_score"] - persona["before_score"]
        persona["bottleneck_edges_before"] = before_bottlenecks
        persona["bottleneck_edges_after"] = after_bottlenecks
        persona["scoring_basis"] = "PERS-inspired weighted link/crossing score, adapted to available OSM/LTA proxy risks."

        ranked = sorted(
            payload["edges"],
            key=lambda e: (
                e["personas"][persona_id]["pers_delta"],
                -e["personas"][persona_id]["pers_before_score"],
            ),
            reverse=True,
        )
        persona["top_bottlenecks"] = [
            {
                "edge_id": e["id"],
                "coords": e["coords"],
                "before_score": e["personas"][persona_id]["pers_before_score"],
                "after_score": e["personas"][persona_id]["pers_after_score"],
                "improvement": e["personas"][persona_id]["pers_delta"],
                "risk_tags": e.get("pers_risk_tags", []),
                "explanation": "PERS-style low-scoring segment: " + ", ".join(
                    SCORING_METHODOLOGY["criteria_mapping"].get(t, t)
                    for t in e.get("pers_risk_tags", [])
                ),
            }
            for e in ranked[:8]
        ]

    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(
        "updated PERS-inspired scoring:",
        {k: (v["before_score"], v["after_score"], v["bottleneck_edges_before"], v["bottleneck_edges_after"])
         for k, v in payload["personas"].items()},
    )


if __name__ == "__main__":
    main()
