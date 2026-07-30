from __future__ import annotations

from dataclasses import dataclass, asdict
import random
from typing import Any


@dataclass(frozen=True)
class PersonaType:
    external_id: str
    label: str
    category: str
    color: str
    resident_weight: float
    visitor_weight: float
    description: str
    mobility_profile: dict[str, Any]
    schedule_profile: dict[str, Any]


@dataclass(frozen=True)
class PersonaAgent:
    external_id: str
    display_name: str
    persona_type_id: str
    resident_status: str
    age_band: str
    sex: str
    home_subzone: str | None
    baseline_speed_mps: float
    routine_seed: int
    traits: dict[str, Any]

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


PERSONA_TYPES: dict[str, PersonaType] = {
    "older_resident_cane": PersonaType("older_resident_cane", "Older resident with cane", "disabled", "#F2994A", 0.11, 0.02, "Older Clementi resident who uses a cane and needs short, stable, sheltered trips.", {"clear_width_need_m": 0.9, "weather_sensitivity": 0.75, "rest_need": 0.8}, {"morning": ["market", "clinic"], "evening": ["short_walk"]}),
    "older_resident_walker": PersonaType("older_resident_walker", "Older resident with walker", "disabled", "#D97904", 0.10, 0.01, "Older resident using a walker, highly sensitive to kerbs, slopes, rest gaps and surface roughness.", {"clear_width_need_m": 1.2, "weather_sensitivity": 0.9, "rest_need": 0.95}, {"midday": ["clinic", "market"]}),
    "wheelchair_user_commuter": PersonaType("wheelchair_user_commuter", "Wheelchair user commuter", "disabled", "#2F80ED", 0.06, 0.04, "Wheelchair user who needs step-free routes, kerb ramps, bus access, lifts and clear paths.", {"clear_width_need_m": 1.5, "kerb_sensitivity": 1.0, "bus_bay_need": 1.0}, {"morning": ["commute"], "evening": ["return_home"]}),
    "visually_impaired_commuter": PersonaType("visually_impaired_commuter", "Visually impaired commuter", "disabled", "#BB6BD9", 0.05, 0.03, "Commuter who relies on tactile guidance, contrast and predictable crossings.", {"wayfinding_sensitivity": 1.0, "crowd_sensitivity": 0.75}, {"morning": ["commute"], "midday": ["errand"]}),
    "pma_pmd_user": PersonaType("pma_pmd_user", "PMA / PMD user", "disabled", "#56CCF2", 0.05, 0.02, "Mobility-device user sensitive to bollards, narrow paths and crowded conflict points.", {"clear_width_need_m": 1.2, "obstruction_sensitivity": 1.0}, {"midday": ["errand"], "evening": ["return_home"]}),
    "caregiver_with_disabled_person": PersonaType("caregiver_with_disabled_person", "Caregiver with disabled person", "access_relevant", "#9B51E0", 0.05, 0.04, "Caregiver accompanying someone with mobility or sensory needs.", {"group_size": 2, "patience": 0.55}, {"midday": ["clinic", "mall"]}),
    "parent_with_stroller": PersonaType("parent_with_stroller", "Parent with stroller", "access_relevant", "#27AE60", 0.09, 0.06, "Parent with stroller who uses ramps, lifts and sometimes competes for bus wheelchair bays.", {"clear_width_need_m": 1.2, "bus_bay_need": 0.8}, {"morning": ["school_dropoff"], "evening": ["pickup"]}),
    "primary_school_child": PersonaType("primary_school_child", "Primary school child", "general", "#F2C94C", 0.08, 0.02, "Child pedestrian concentrated around school peaks and crossings.", {"crossing_sensitivity": 0.8, "speed_mps": 1.0}, {"morning": ["school"], "afternoon": ["return_home"]}),
    "secondary_student": PersonaType("secondary_student", "Secondary student", "general", "#F7D774", 0.07, 0.05, "Teen student using bus/MRT and school routes.", {"speed_mps": 1.25}, {"morning": ["school"], "afternoon": ["mall", "return_home"]}),
    "poly_uni_student": PersonaType("poly_uni_student", "Poly / university student", "general", "#FFFFFF", 0.04, 0.15, "Inbound or resident tertiary student drawn by NUS/SIM/SUSS/NP/SP/Dover.", {"speed_mps": 1.3}, {"morning": ["campus"], "evening": ["mrt"]}),
    "working_adult_commuter": PersonaType("working_adult_commuter", "Working adult commuter", "general", "#111827", 0.21, 0.16, "General commuter mass affecting crowding, queueing and path pressure.", {"speed_mps": 1.35}, {"morning": ["commute"], "evening": ["return_home"]}),
    "delivery_rider_worker": PersonaType("delivery_rider_worker", "Delivery / service worker", "access_relevant", "#EB5757", 0.09, 0.10, "Fast-moving worker who can create footpath conflict or temporary obstruction pressure.", {"conflict_externality": 0.8, "speed_mps": 1.55}, {"midday": ["deliveries"], "evening": ["deliveries"]}),
}

SUBZONES = ["Clementi Central", "Clementi North", "Clementi Woods", "West Coast", "Dover", "Faber", "Pandan", "Sunset Way", "Toh Tuck"]
SEXES = ["female", "male"]
AGE_BY_PERSONA = {
    "older_resident_cane": "65-79",
    "older_resident_walker": "75+",
    "wheelchair_user_commuter": "25-64",
    "visually_impaired_commuter": "25-64",
    "pma_pmd_user": "45-74",
    "parent_with_stroller": "25-44",
    "primary_school_child": "5-12",
    "secondary_student": "13-18",
    "poly_uni_student": "18-29",
    "working_adult_commuter": "25-64",
    "caregiver_with_disabled_person": "35-64",
    "delivery_rider_worker": "18-54",
}
BASE_SPEED = {
    "older_resident_cane": 0.75,
    "older_resident_walker": 0.55,
    "wheelchair_user_commuter": 0.85,
    "visually_impaired_commuter": 0.95,
    "pma_pmd_user": 1.0,
    "caregiver_with_disabled_person": 0.8,
    "parent_with_stroller": 0.9,
    "primary_school_child": 1.0,
    "secondary_student": 1.2,
    "poly_uni_student": 1.3,
    "working_adult_commuter": 1.35,
    "delivery_rider_worker": 1.55,
}


def _weighted_persona_ids() -> list[str]:
    weighted: list[str] = []
    # Demo panel weights intentionally oversample disabled/access-relevant personas while preserving general flow.
    counts = {
        "working_adult_commuter": 70,
        "poly_uni_student": 35,
        "secondary_student": 20,
        "primary_school_child": 18,
        "older_resident_cane": 25,
        "older_resident_walker": 25,
        "parent_with_stroller": 30,
        "wheelchair_user_commuter": 18,
        "visually_impaired_commuter": 15,
        "pma_pmd_user": 15,
        "caregiver_with_disabled_person": 9,
        "delivery_rider_worker": 20,
    }
    for pid, count in counts.items():
        weighted.extend([pid] * count)
    return weighted


def generate_agents(count: int, seed: int = 42) -> list[PersonaAgent]:
    rng = random.Random(seed)
    weighted = _weighted_persona_ids()
    agents: list[PersonaAgent] = []
    for idx in range(count):
        persona_id = weighted[idx % len(weighted)] if count >= len(weighted) else rng.choice(weighted)
        persona = PERSONA_TYPES[persona_id]
        resident_status = "resident" if rng.random() < max(0.25, persona.resident_weight / max(persona.resident_weight + persona.visitor_weight, 0.01)) else "worker_student_inbound"
        if persona_id in {"poly_uni_student", "delivery_rider_worker"} and rng.random() < 0.65:
            resident_status = "worker_student_inbound"
        name = f"{persona.label.split()[0]} Agent {idx + 1:03d}"
        speed = max(0.35, BASE_SPEED[persona_id] + rng.uniform(-0.08, 0.08))
        agents.append(
            PersonaAgent(
                external_id=f"agent_{seed}_{idx + 1:04d}",
                display_name=name,
                persona_type_id=persona_id,
                resident_status=resident_status,
                age_band=AGE_BY_PERSONA[persona_id],
                sex=rng.choice(SEXES),
                home_subzone=rng.choice(SUBZONES) if resident_status == "resident" else None,
                baseline_speed_mps=round(speed, 2),
                routine_seed=rng.randint(1, 2_000_000_000),
                traits={
                    "weather_sensitivity": round(float(persona.mobility_profile.get("weather_sensitivity", rng.uniform(0.2, 0.65))), 2),
                    "crowd_sensitivity": round(float(persona.mobility_profile.get("crowd_sensitivity", rng.uniform(0.2, 0.8))), 2),
                    "feedback_propensity": round(0.25 + (0.35 if persona.category == "disabled" else 0.1) + rng.uniform(0, 0.2), 2),
                },
            )
        )
    return agents
