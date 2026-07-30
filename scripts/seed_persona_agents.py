#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulation.synthetic_population import PERSONA_TYPES, generate_agents
DEFAULT_OUT = ROOT / "data/live_persona_agents_seed.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed evidence-based JalanLens persona agents for the live simulation.")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    agents = generate_agents(args.count, seed=args.seed)
    payload = {
        "source": "JalanLens synthetic simulation panel",
        "note": "Synthetic, not real-person tracking. Disabled/access-relevant personas are intentionally oversampled for accessibility stress testing.",
        "persona_types": {pid: persona.__dict__ for pid, persona in PERSONA_TYPES.items()},
        "agents": [agent.to_row() for agent in agents],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    print(f"wrote {args.output}")
    print(f"persona_types: {len(payload['persona_types'])}")
    print(f"agents: {len(payload['agents'])}")


if __name__ == "__main__":
    main()
