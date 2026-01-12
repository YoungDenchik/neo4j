from __future__ import annotations

from typing import List
from services.risk_analysis_service import RiskSignal
from domain.models import PersonProfile


class LLMService:
    """
    Production best-practice:
    - LLM does NOT access DB directly
    - LLM explains structured results
    - can be swapped with OpenAI/local model
    """

    def explain_risk(self, profile: PersonProfile, signals: List[RiskSignal]) -> str:
        # Тут буде інтеграція з LLM.
        # Поки — deterministic placeholder.
        lines = [
            f"Risk explanation for {profile.person.name} ({profile.person.person_id}):",
            f"- Direct assets: {len(profile.assets_direct)} items",
            f"- Indirect assets via companies: {len(profile.assets_indirect)} items",
            "",
            "Signals:"
        ]
        for s in signals:
            lines.append(f"- [{s.severity}] {s.code}: {s.title} | details={s.details}")
        return "\n".join(lines)
