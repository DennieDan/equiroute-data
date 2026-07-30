import os
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from simulation.clock import day_phase, singapore_now
from simulation.synthetic_population import PERSONA_TYPES, generate_agents
from simulation.agent_model import build_agent_live_states, aggregate_street_part_counts
from simulation.feedback_policy import build_agent_feedback_thread, filter_combined_feedback, merge_feedback_threads
from simulation.model_provider import choose_free_model_provider


class LivePersonaSimulationTests(unittest.TestCase):
    def test_singapore_clock_uses_gmt_plus_8(self):
        now = singapore_now()
        self.assertEqual(now.tzinfo, ZoneInfo("Asia/Singapore"))
        self.assertEqual(now.utcoffset().total_seconds(), 8 * 3600)
        self.assertEqual(day_phase(datetime(2026, 7, 30, 8, 15, tzinfo=ZoneInfo("Asia/Singapore"))), "morning_peak")
        self.assertEqual(day_phase(datetime(2026, 7, 30, 23, 15, tzinfo=ZoneInfo("Asia/Singapore"))), "night")

    def test_synthetic_agents_include_disabled_and_public_relevant_personas(self):
        agents = generate_agents(300, seed=42)
        self.assertEqual(len(agents), 300)
        persona_ids = {a.persona_type_id for a in agents}
        self.assertIn("wheelchair_user_commuter", persona_ids)
        self.assertIn("parent_with_stroller", persona_ids)
        self.assertIn("working_adult_commuter", persona_ids)
        disabled = sum(1 for a in agents if PERSONA_TYPES[a.persona_type_id].category == "disabled")
        public_relevant = sum(1 for a in agents if PERSONA_TYPES[a.persona_type_id].category == "access_relevant")
        self.assertGreater(disabled, 40)  # intentionally oversampled panel for the demo
        self.assertGreater(public_relevant, 40)
        self.assertTrue(all(a.display_name and a.external_id.startswith("agent_") for a in agents))

    def test_live_states_and_counts_are_per_agent_and_per_persona(self):
        agents = generate_agents(12, seed=7)
        states = build_agent_live_states(agents, tick_index=3)
        self.assertEqual(len(states), 12)
        self.assertTrue(all(s.agent_external_id.startswith("agent_") for s in states))
        counts = aggregate_street_part_counts(states)
        self.assertGreaterEqual(len(counts), 1)
        first = counts[0]
        self.assertIn("persona_counts", first)
        self.assertEqual(first["total_count"], sum(first["persona_counts"].values()))

    def test_agent_feedback_is_separate_but_mergeable_with_public_threads(self):
        agent = generate_agents(1, seed=3)[0]
        thread = build_agent_feedback_thread(
            agent=agent,
            street_part_id="street-part-db-1",
            street_part_external_id="footpath_0001",
            blocker_kind="bus_bay_conflict",
            severity=0.91,
            persona_type=PERSONA_TYPES[agent.persona_type_id],
            occurred_at=datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(thread["source"], "agent_simulation")
        self.assertEqual(thread["agent_external_id"], agent.external_id)
        self.assertIsNone(thread.get("created_by"))
        self.assertEqual(thread["persona_type"], agent.persona_type_id)
        self.assertIn("agent_feedback_threads", thread["target_table"])

        public = [{"id": "p1", "source": "public", "created_at": "2026-07-30T08:00:00+08:00", "persona_type": "wheelchair_user_commuter", "title": "public"}]
        combined = merge_feedback_threads(public, [thread])
        self.assertEqual({row["source"] for row in combined}, {"public", "agent_simulation"})
        self.assertEqual(len(filter_combined_feedback(combined, source="agent_simulation")), 1)
        self.assertEqual(len(filter_combined_feedback(combined, source="public")), 1)
        self.assertEqual(len(filter_combined_feedback(combined, persona_type=agent.persona_type_id)), 1)
        self.assertEqual(len(filter_combined_feedback(combined, recency="today", now=datetime(2026, 7, 30, 12, tzinfo=timezone.utc))), 2)

    def test_free_model_provider_prefers_existing_agnes_key_for_feedback_generation(self):
        provider = choose_free_model_provider({"AGNES_API_KEY": "agnes-key", "OPENROUTER_API_KEY": "or-key", "SEA_LION_API_KEY": "sea-key"})
        self.assertEqual(provider.name, "agnes")
        self.assertEqual(provider.model, "agnes-2.0-flash")
        self.assertIn("20 rpm", provider.reason.lower())
        fallback = choose_free_model_provider({})
        self.assertEqual(fallback.name, "deterministic")


if __name__ == "__main__":
    unittest.main()
