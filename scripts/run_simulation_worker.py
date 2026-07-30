#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulation.agent_model import aggregate_street_part_counts, build_agent_live_states
from simulation.feedback_policy import build_agent_feedback_thread
from simulation.model_provider import choose_free_model_provider
from simulation.synthetic_population import PERSONA_TYPES, generate_agents

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data/live_persona_simulation_snapshot.json"


def _write_snapshot(path: Path, tick_index: int, agent_count: int, seed: int) -> dict:
    agents = generate_agents(agent_count, seed=seed)
    agent_by_id = {agent.external_id: agent for agent in agents}
    states = build_agent_live_states(agents, tick_index=tick_index)
    counts = aggregate_street_part_counts(states)
    now = datetime.now(timezone.utc)
    feedback = []
    affected_states = [s for s in states if PERSONA_TYPES[agent_by_id[s.agent_external_id].persona_type_id].category in {"disabled", "access_relevant"}]
    for state in affected_states[:6]:
        agent = agent_by_id[state.agent_external_id]
        persona = PERSONA_TYPES[agent.persona_type_id]
        if persona.category in {"disabled", "access_relevant"}:
            event = "bus_bay_conflict" if agent.persona_type_id in {"wheelchair_user_commuter", "parent_with_stroller"} else "crowding_or_weather_friction"
            feedback.append(
                build_agent_feedback_thread(
                    agent=agent,
                    street_part_id=None,
                    street_part_external_id=state.street_part_external_id,
                    blocker_kind=event,
                    severity=0.72,
                    persona_type=persona,
                    occurred_at=now,
                )
            )
    provider = choose_free_model_provider(os.environ)
    payload = {
        "project": "JalanLens live persona simulation",
        "tick_index": tick_index,
        "generated_at": now.isoformat(),
        "model_provider": provider.__dict__,
        "persona_types": {pid: persona.__dict__ for pid, persona in PERSONA_TYPES.items()},
        "note": "Rules-based live simulation; free model is reserved for occasional feedback wording/deduplication, not per-agent ticks.",
        "agent_live_states": [s.to_row() for s in states],
        "street_part_agent_counts": counts,
        "agent_feedback_threads": feedback,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or snapshot the JalanLens live persona simulation worker.")
    parser.add_argument("--agent-count", type=int, default=int(os.getenv("SIM_AGENT_COUNT", "300")))
    parser.add_argument("--seed", type=int, default=int(os.getenv("SIM_SEED", "42")))
    parser.add_argument("--tick-seconds", type=int, default=int(os.getenv("SIM_TICK_SECONDS", "10")))
    parser.add_argument("--once", action="store_true", help="Write one local JSON snapshot and exit.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    tick = 0
    while True:
        payload = _write_snapshot(args.output, tick, args.agent_count, args.seed)
        print(f"tick={tick} agents={len(payload['agent_live_states'])} parts={len(payload['street_part_agent_counts'])} feedback={len(payload['agent_feedback_threads'])} output={args.output}", flush=True)
        if args.once:
            break
        tick += 1
        time.sleep(args.tick_seconds)


if __name__ == "__main__":
    main()
