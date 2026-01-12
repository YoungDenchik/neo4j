from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from domain.models import PersonProfile


@dataclass(frozen=True)
class RiskSignal:
    code: str
    severity: str  # "LOW" | "MEDIUM" | "HIGH"
    title: str
    details: Dict[str, Any]


class RiskAnalysisService:
    """
    Deterministic analysis:
    - DO NOT ask LLM to "find anomalies"
    - produce structured signals
    """

    def __init__(self, asset_value_threshold: float = 1_000_000.0):
        self.asset_value_threshold = asset_value_threshold

    def analyze_profile(self, profile: PersonProfile) -> List[RiskSignal]:
        signals: List[RiskSignal] = []

        # Example signal 1: high-value direct assets
        total_direct = sum([a.value or 0.0 for a in profile.assets_direct])
        if total_direct >= self.asset_value_threshold:
            signals.append(
                RiskSignal(
                    code="HIGH_DIRECT_ASSETS",
                    severity="MEDIUM",
                    title="High total value of directly owned assets",
                    details={"total_direct_assets_value": total_direct, "threshold": self.asset_value_threshold},
                )
            )

        # Example signal 2: indirect assets exist (via companies)
        if len(profile.assets_indirect) > 0:
            total_indirect = sum([a.value or 0.0 for a in profile.assets_indirect])
            signals.append(
                RiskSignal(
                    code="INDIRECT_ASSETS_VIA_COMPANIES",
                    severity="MEDIUM",
                    title="Assets potentially controlled via companies",
                    details={"count": len(profile.assets_indirect), "total_indirect_assets_value": total_indirect},
                )
            )

        return signals
