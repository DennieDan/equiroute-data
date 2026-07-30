from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Any

from .synthetic_population import PersonaAgent

# Clementi Mall / Clementi Central demo bounds. Worker can later replace this with street_part geometries from Supabase.
STREET_PART_ANCHORS = [
    ("street_part_0000", 103.76480, 1.31395),
    ("street_part_0001", 103.76515, 1.31355),
    ("street_part_0002", 103.76555, 1.31310),
    ("street_part_0003", 103.76600, 1.31265),
    ("street_part_0004", 103.76640, 1.31220),
    ("street_part_0005", 103.76680, 1.31178),
    ("street_part_0006", 103.76720, 1.31135),
    ("street_part_0007", 103.76765, 1.31092),
]


@dataclass(frozen=True)
class AgentLiveState:
    agent_external_id: str
    persona_type_id: str
    display_name: str
    activity: str
    lng: float
    lat: float
    street_part_external_id: str
    state: dict[str, Any]

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


def _activity_for(agent: PersonaAgent, tick_index: int) -> str:
    phase = tick_index % 24
    if phase in range(0, 6):
        return "sleep"
    if phase in range(7, 10):
        if "student" in agent.persona_type_id or "child" in agent.persona_type_id:
            return "commute_to_school"
        if "stroller" in agent.persona_type_id:
            return "school_dropoff"
        return "commute"
    if phase in range(10, 15):
        if "older" in agent.persona_type_id:
            return "market_or_clinic"
        if "delivery" in agent.persona_type_id:
            return "deliveries"
        return "work_school_or_errand"
    if phase in range(17, 20):
        return "return_home"
    return "local_errand"


def build_agent_live_states(agents: list[PersonaAgent], tick_index: int = 0) -> list[AgentLiveState]:
    states: list[AgentLiveState] = []
    total = max(1, len(STREET_PART_ANCHORS))
    for idx, agent in enumerate(agents):
        anchor_idx = (idx + tick_index + agent.routine_seed % total) % total
        part_id, base_lng, base_lat = STREET_PART_ANCHORS[anchor_idx]
        wobble = (agent.routine_seed % 97) / 97
        lng = base_lng + math.sin(tick_index / 3 + wobble) * 0.00008
        lat = base_lat + math.cos(tick_index / 3 + wobble) * 0.00006
        crowd_pressure = 0.2 + ((idx + tick_index) % 9) / 10
        states.append(
            AgentLiveState(
                agent_external_id=agent.external_id,
                persona_type_id=agent.persona_type_id,
                display_name=agent.display_name,
                activity=_activity_for(agent, tick_index),
                lng=round(lng, 7),
                lat=round(lat, 7),
                street_part_external_id=part_id,
                state={
                    "speed_mps": agent.baseline_speed_mps,
                    "crowd_pressure": round(crowd_pressure, 2),
                    "route_outcome": "moving",
                },
            )
        )
    return states


def aggregate_street_part_counts(states: list[AgentLiveState]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for state in states:
        row = grouped.setdefault(state.street_part_external_id, {"street_part_external_id": state.street_part_external_id, "persona_counts": {}, "total_count": 0})
        row["persona_counts"][state.persona_type_id] = row["persona_counts"].get(state.persona_type_id, 0) + 1
        row["total_count"] += 1
    return sorted(grouped.values(), key=lambda row: row["street_part_external_id"])
