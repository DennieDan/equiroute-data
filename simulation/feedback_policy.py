from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .synthetic_population import PersonaAgent, PersonaType

RECENCY_WINDOWS = {
    "today": timedelta(days=1),
    "3d": timedelta(days=3),
    "past_3_days": timedelta(days=3),
    "week": timedelta(days=7),
    "past_week": timedelta(days=7),
}


def build_agent_feedback_thread(
    *,
    agent: PersonaAgent,
    street_part_id: str | None,
    street_part_external_id: str,
    blocker_kind: str,
    severity: float,
    persona_type: PersonaType,
    occurred_at: datetime,
) -> dict[str, Any]:
    title = f"{persona_type.label} friction near {street_part_external_id.replace('_', ' ')}"
    body = (
        f"Simulated agent {agent.display_name} ({agent.external_id}) experienced {blocker_kind.replace('_', ' ')} "
        f"with severity {severity:.2f}. This is agent-simulation feedback, stored separately from human public feedback but shown together for authority review."
    )
    return {
        "target_table": "agent_feedback_threads",
        "source": "agent_simulation",
        "agent_external_id": agent.external_id,
        "agent_name": agent.display_name,
        "persona_type": agent.persona_type_id,
        "street_part_id": street_part_id,
        "street_part_external_id": street_part_external_id,
        "feature_id": None,
        "event_type": blocker_kind,
        "severity": round(float(severity), 3),
        "title": title,
        "body": body,
        "status": "open",
        "priority_score": round(max(0.0, min(1.0, severity)) * 100),
        "created_at": occurred_at.isoformat(),
        "created_by": None,
    }


def merge_feedback_threads(public_threads: list[dict[str, Any]], agent_threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in public_threads:
        rows.append({**row, "source": row.get("source") or "public"})
    for row in agent_threads:
        rows.append({**row, "source": row.get("source") or "agent_simulation"})
    return sorted(rows, key=lambda row: row.get("created_at") or "", reverse=True)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def filter_combined_feedback(
    rows: list[dict[str, Any]],
    *,
    source: str = "all",
    persona_type: str = "all",
    recency: str = "all",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    window = RECENCY_WINDOWS.get(recency)
    out = []
    for row in rows:
        if source != "all" and row.get("source") != source:
            continue
        if persona_type != "all" and row.get("persona_type") != persona_type:
            continue
        if window is not None:
            created = _parse_dt(row.get("created_at"))
            if not created:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if now - created.astimezone(timezone.utc) > window:
                continue
        out.append(row)
    return out
