from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class FreeModelProvider:
    name: str
    base_url: str | None
    model: str
    env_key: str | None
    reason: str


def choose_free_model_provider(env: Mapping[str, str]) -> FreeModelProvider:
    """Choose a free/zero-marginal-cost model for occasional agent feedback text.

    We do not call an LLM per agent tick. The simulation is rules-based; an LLM is
    only used to polish/deduplicate occasional feedback summaries. Based on current
    public quotas, Agnes is preferred when credentials exist because free/default
    text access is documented around 20 executable RPM, higher than SEA-LION's 10
    RPM and more practical than OpenRouter accounts without purchased credits.
    """
    if env.get("AGNES_API_KEY"):
        return FreeModelProvider(
            name="agnes",
            base_url="https://apihub.agnes-ai.com/v1",
            model="agnes-2.0-flash",
            env_key="AGNES_API_KEY",
            reason="Best available existing credential; Agnes free/default text quota is documented around 20 rpm and the model is intended for agent workflows.",
        )
    if env.get("OPENROUTER_API_KEY"):
        return FreeModelProvider(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model="qwen/qwen3-coder:free",
            env_key="OPENROUTER_API_KEY",
            reason="Useful fallback, but free models have daily request caps unless credits were previously purchased.",
        )
    if env.get("SEA_LION_API_KEY") or env.get("SEALION_API_KEY"):
        return FreeModelProvider(
            name="sea-lion",
            base_url="https://api.sea-lion.ai/v1",
            model="aisingapore/Qwen-SEA-LION-v4.5-27B-IT",
            env_key="SEA_LION_API_KEY" if env.get("SEA_LION_API_KEY") else "SEALION_API_KEY",
            reason="Strong Southeast Asia context, but lower documented trial rate limit around 10 rpm.",
        )
    return FreeModelProvider(
        name="deterministic",
        base_url=None,
        model="rules-only-feedback-template",
        env_key=None,
        reason="No free-model API key is configured; use deterministic feedback templates with no model calls.",
    )
