"""
Decision service that combines Fuzzy Logic and AHP into ranked recommendations.
Implements human-in-the-loop override support and a rule-based multi-suggestion engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import logging

from app.database.mongodb import MongoDBConnection
from app.database.supabase import SupabaseConnection
from app.models.schemas import RecommendedAction, RiskLevel
from app.services.ahp_service import AHPService
from app.services.fuzzy_service import FuzzyLogicService

logger = logging.getLogger(__name__)

MIN_SUGGESTIONS = 3

# Ordered pool for padding (urgencies below routine rules so real signals outrank fillers)
_FALLBACK_POOL: List[Tuple[RecommendedAction, float, float, str]] = [
    (
        RecommendedAction.PREPARE,
        22.0,
        0.58,
        "Baseline readiness while conditions are monitored against thresholds",
    ),
    (
        RecommendedAction.MONITOR,
        20.0,
        0.55,
        "Maintain sensor and field monitoring for the next assessment window",
    ),
    (
        RecommendedAction.PARTIAL_EVACUATION,
        18.0,
        0.52,
        "Standby partial evacuation capacity in case water or vulnerability signals worsen",
    ),
    (
        RecommendedAction.DEPLOY_RESCUE_TEAM,
        16.0,
        0.50,
        "Pre-position rescue capacity for rapid deployment if risk escalates",
    ),
    (
        RecommendedAction.SEND_MEDICAL_ASSISTANCE,
        14.0,
        0.50,
        "Ensure medical teams are on alert for vulnerable households",
    ),
    (
        RecommendedAction.PREPARE_FOOD_PACKS,
        12.0,
        0.48,
        "Stage food packs in case relief distribution is needed soon",
    ),
    (
        RecommendedAction.PREPARE_ADDITIONAL_RESOURCES,
        10.0,
        0.46,
        "Potential escalation risk within the next monitoring window",
    ),
]


@dataclass(frozen=True)
class _RawSuggestion:
    action: RecommendedAction
    reason: str
    urgency: float
    confidence_score: float


class DecisionService:
    """
    Combines fuzzy logic risk assessment with AHP vulnerability scoring
    to produce ranked, explainable relief recommendations.

    Ranking: highest urgency first, then highest confidence (deterministic tie-break).
    """

    HIGH_PRIORITY_THRESHOLD = 0.65
    MEDIUM_PRIORITY_THRESHOLD = 0.35

    @classmethod
    def make_decision(
        cls,
        barangay_id: int,
        override_action: Optional[RecommendedAction] = None,
    ) -> Dict[str, Any]:
        """
        Make a relief allocation decision for a barangay.

        Returns a dict including at least three ranked ``suggestions`` plus legacy fields.
        """
        logger.info(f"Making decision for barangay {barangay_id}")

        try:
            sensor_data = MongoDBConnection.get_sensor_data(barangay_id, minutes=10)

            fuzzy_result = FuzzyLogicService.assess_risk(
                avg_water_level=sensor_data["avg_water_level"],
                max_water_level=sensor_data["max_water_level"],
                trend=sensor_data["trend"],
            )

            household_data = SupabaseConnection.get_household_vulnerability(barangay_id)

            ahp_result = AHPService.calculate_priority(
                elderly_count=household_data["elderly_count"],
                infant_count=household_data["infant_count"],
                pregnant_count=household_data["pregnant_count"],
                pwd_count=household_data["pwd_count"],
                total_residents=household_data.get("total_residents", 5),
            )

            suggestions = cls._build_ranked_suggestions(
                fuzzy_result=fuzzy_result,
                ahp_result=ahp_result,
            )

            recommendation = cls._combine_assessments(
                fuzzy_result=fuzzy_result,
                ahp_result=ahp_result,
                override_action=override_action,
                ranked_suggestions=suggestions,
            )

            logger.info(
                f"Decision made for barangay {barangay_id}: "
                f"{recommendation['recommended_action']} "
                f"(top suggestion confidence: {suggestions[0]['confidence_score']:.2f})"
            )

            return {
                "barangay_id": barangay_id,
                "risk_level": fuzzy_result["risk_level"],
                "priority_score": ahp_result["priority_score"],
                "suggestions": suggestions,
                "recommended_action": recommendation["recommended_action"],
                "confidence_score": recommendation["confidence_score"],
                "explanation": recommendation["summary_explanation"],
                "override_action": override_action,
                "fuzzy_explanation": fuzzy_result["explanation"],
                "ahp_explanation": ahp_result["explanation"],
                "_metadata": {
                    "sensor_readings_count": sensor_data.get("readings_count", 0),
                    "total_residents": household_data.get("total_residents", 0),
                    "vulnerability_factors": ahp_result.get("vulnerability_factors", []),
                },
            }

        except Exception as e:
            logger.error(f"Error making decision for barangay {barangay_id}: {str(e)}")
            fallback_suggestions = cls._error_fallback_suggestions(str(e))
            return {
                "barangay_id": barangay_id,
                "risk_level": RiskLevel.MEDIUM,
                "priority_score": 0.5,
                "suggestions": fallback_suggestions,
                "recommended_action": RecommendedAction.PREPARE,
                "confidence_score": 0.3,
                "explanation": (
                    f"Decision system error: {str(e)}. Recommend PREPARE as precaution; "
                    "suggestions below are conservative fallbacks."
                ),
                "override_action": override_action,
                "fuzzy_explanation": "Error retrieving sensor data",
                "ahp_explanation": "Error retrieving household data",
                "_metadata": {"error": str(e)},
            }

    @classmethod
    def _error_fallback_suggestions(cls, err: str) -> List[Dict[str, Any]]:
        """At least three safe, generic suggestions when upstream data fails."""
        return [
            {
                "priority_rank": 1,
                "action": RecommendedAction.PREPARE,
                "confidence_score": 0.45,
                "reason": f"System degraded ({err[:120]}...); default to preparedness",
            },
            {
                "priority_rank": 2,
                "action": RecommendedAction.MONITOR,
                "confidence_score": 0.42,
                "reason": "Verify sensor and household data manually before stronger actions",
            },
            {
                "priority_rank": 3,
                "action": RecommendedAction.PREPARE_ADDITIONAL_RESOURCES,
                "confidence_score": 0.40,
                "reason": "Stage resources until automated assessment recovers",
            },
        ]

    @classmethod
    def _risk_str(cls, fuzzy_result: Dict[str, Any]) -> str:
        rl = fuzzy_result["risk_level"]
        return rl.value if isinstance(rl, RiskLevel) else str(rl)

    @classmethod
    def _collect_rule_candidates(
        cls,
        fuzzy_result: Dict[str, Any],
        ahp_result: Dict[str, Any],
    ) -> List[_RawSuggestion]:
        """Rule-based candidates: no ML; each rule is auditable."""
        risk = cls._risk_str(fuzzy_result)
        trend = str(fuzzy_result.get("trend", "stable")).lower()
        risk_conf = float(fuzzy_result["confidence_score"])
        priority = float(ahp_result["priority_score"])

        high_p = priority >= cls.HIGH_PRIORITY_THRESHOLD
        med_p = priority >= cls.MEDIUM_PRIORITY_THRESHOLD
        rising = trend == "rising"
        falling = trend == "falling"

        raw: List[_RawSuggestion] = []

        def conf(base: float) -> float:
            return max(0.0, min(1.0, base))

        # --- Immediate / rescue / medical (high urgency) ---
        if risk == "HIGH" and high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.IMMEDIATE_RELIEF,
                    "High flood levels and highly vulnerable households",
                    100.0,
                    conf(min(0.95, risk_conf + 0.12)),
                )
            )
        elif risk == "MEDIUM" and high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.IMMEDIATE_RELIEF,
                    "Elevated flood risk with high household vulnerability warrants urgent relief",
                    92.0,
                    conf(risk_conf * 0.92 + priority * 0.08),
                )
            )

        if risk == "HIGH":
            raw.append(
                _RawSuggestion(
                    RecommendedAction.DEPLOY_RESCUE_TEAM,
                    "High classified flood risk requires rescue capacity on standby or deployed",
                    86.0,
                    conf(risk_conf * 0.88 + (0.05 if rising else 0.0)),
                )
            )

        if high_p and risk != "LOW":
            raw.append(
                _RawSuggestion(
                    RecommendedAction.SEND_MEDICAL_ASSISTANCE,
                    "Vulnerable household composition elevates medical support priority",
                    78.0,
                    conf(0.72 * risk_conf + 0.28 * priority),
                )
            )

        if risk in ("HIGH", "MEDIUM") and rising:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PARTIAL_EVACUATION,
                    "Flood trend is rapidly rising; staged evacuation reduces exposure",
                    84.0 if risk == "HIGH" else 72.0,
                    conf(risk_conf * 0.85 + (0.1 if rising else 0.0)),
                )
            )

        if risk == "HIGH" and med_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE_FOOD_PACKS,
                    "High water risk with moderate vulnerability; pre-stage food distribution",
                    68.0,
                    conf(risk_conf * 0.82 + priority * 0.1),
                )
            )

        if risk in ("HIGH", "MEDIUM") and (rising or (risk == "HIGH" and stable)):
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE_ADDITIONAL_RESOURCES,
                    "Potential escalation within the next monitoring window given level and trend",
                    66.0 if rising else 58.0,
                    conf(risk_conf * 0.78 + (0.08 if rising else -0.05)),
                )
            )

        if risk == "MEDIUM" and med_p and not high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE,
                    "Medium flood risk with moderate vulnerability; readiness and routing checks",
                    56.0,
                    conf((risk_conf + priority) / 2 * 0.88),
                )
            )

        if risk == "MEDIUM" and not med_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.MONITOR,
                    "Medium environmental risk with lower demographic vulnerability; intensify monitoring",
                    48.0,
                    conf(risk_conf * 0.8),
                )
            )

        if risk == "LOW" and high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE,
                    "Water levels are low but vulnerable residents warrant contingency preparation",
                    44.0,
                    conf(risk_conf * 0.75 + priority * 0.15),
                )
            )

        if risk == "LOW" and not high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.SAFE,
                    "Low flood risk and limited vulnerability indicators at this assessment",
                    35.0,
                    conf(risk_conf * 0.88),
                )
            )
            raw.append(
                _RawSuggestion(
                    RecommendedAction.MONITOR,
                    "Maintain routine monitoring despite favorable flood signals",
                    30.0,
                    conf(0.55 + (0.05 if falling else 0.0)),
                )
            )

        if risk == "HIGH" and not high_p and not med_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE,
                    "High water risk with lower recorded demographic vulnerability; still pre-position assets",
                    62.0,
                    conf(risk_conf * 0.84),
                )
            )

        return raw

    @classmethod
    def _dedupe_merge(cls, candidates: List[_RawSuggestion]) -> List[_RawSuggestion]:
        """One entry per action: keep highest urgency, then confidence."""
        best: Dict[RecommendedAction, _RawSuggestion] = {}
        for c in candidates:
            prev = best.get(c.action)
            if prev is None:
                best[c.action] = c
            elif (c.urgency, c.confidence_score) > (prev.urgency, prev.confidence_score):
                best[c.action] = c
        return list(best.values())

    @classmethod
    def _sort_key(cls, s: _RawSuggestion) -> Tuple[float, float]:
        return (s.urgency, s.confidence_score)

    @classmethod
    def _pad_to_minimum(
        cls,
        merged: List[_RawSuggestion],
    ) -> List[_RawSuggestion]:
        existing = {s.action for s in merged}
        out = list(merged)
        for action, urg, conf, reason in _FALLBACK_POOL:
            if len(out) >= MIN_SUGGESTIONS:
                break
            if action in existing:
                continue
            out.append(_RawSuggestion(action, reason, urg, conf))
            existing.add(action)
        # Absolute last resort duplicates should not happen; if still short, vary ranks only
        idx = 0
        while len(out) < MIN_SUGGESTIONS:
            a, urg, conf, r = _FALLBACK_POOL[idx % len(_FALLBACK_POOL)]
            out.append(
                _RawSuggestion(
                    a,
                    f"{r} (alternate emphasis)",
                    urg - 1.0 - idx,
                    max(0.35, conf - 0.02 * idx),
                )
            )
            idx += 1
        return out

    @classmethod
    def _build_ranked_suggestions(
        cls,
        fuzzy_result: Dict[str, Any],
        ahp_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidates = cls._collect_rule_candidates(fuzzy_result, ahp_result)
        merged = cls._dedupe_merge(candidates)
        merged.sort(key=cls._sort_key, reverse=True)
        padded = cls._pad_to_minimum(merged)
        padded.sort(key=cls._sort_key, reverse=True)

        final = padded[:8]
        ranked: List[Dict[str, Any]] = []
        for i, s in enumerate(final, start=1):
            ranked.append(
                {
                    "priority_rank": i,
                    "action": s.action,
                    "confidence_score": round(s.confidence_score, 4),
                    "reason": s.reason,
                }
            )
        if len(ranked) < MIN_SUGGESTIONS:
            return cls._error_fallback_suggestions("insufficient suggestions")[:MIN_SUGGESTIONS]
        return ranked

    @classmethod
    def _combine_assessments(
        cls,
        fuzzy_result: Dict[str, Any],
        ahp_result: Dict[str, Any],
        override_action: Optional[RecommendedAction],
        ranked_suggestions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if override_action:
            logger.warning(
                "Human override applied: %s (AI ranked list retained for review)",
                override_action,
            )
            return {
                "recommended_action": override_action,
                "confidence_score": 0.95,
                "summary_explanation": (
                    f"Human override applied: {override_action.value}. "
                    "Ranked AI suggestions are advisory only."
                ),
            }

        top = ranked_suggestions[0]
        top_action = top["action"]
        top_conf = float(top["confidence_score"])

        risk = cls._risk_str(fuzzy_result)
        priority = float(ahp_result["priority_score"])

        summary = cls._generate_combined_explanation(
            risk,
            priority,
            top_action,
            top_conf,
        )
        summary += f" Primary ranked suggestion: {top_action.value} — {top['reason']}"

        return {
            "recommended_action": top_action,
            "confidence_score": max(0.0, min(1.0, top_conf)),
            "summary_explanation": summary,
        }

    @classmethod
    def _generate_combined_explanation(
        cls,
        risk_level: str,
        priority_score: float,
        action: RecommendedAction,
        confidence: float,
    ) -> str:
        confidence_pct = int(confidence * 100)
        priority_pct = int(priority_score * 100)

        if priority_score >= 0.65:
            priority_level = "high vulnerability"
        elif priority_score >= 0.35:
            priority_level = "moderate vulnerability"
        else:
            priority_level = "low vulnerability"

        parts = [
            f"Risk level {risk_level} combined with {priority_level} ({priority_pct}%)"
        ]

        if action == RecommendedAction.IMMEDIATE_RELIEF:
            parts.append(
                f"indicates immediate relief is the leading recommendation (confidence: {confidence_pct}%)."
            )
        elif action in (RecommendedAction.PREPARE, RecommendedAction.PREPARE_ADDITIONAL_RESOURCES):
            parts.append(
                f"warrants preparation and resource staging (confidence: {confidence_pct}%)."
            )
        elif action == RecommendedAction.SAFE:
            parts.append(
                f"suggests conditions favor a safe status with continued vigilance (confidence: {confidence_pct}%)."
            )
        else:
            parts.append(
                f"supports action {action.value} as the top ranked option (confidence: {confidence_pct}%)."
            )

        parts.append(f"Official recommendation (rank 1): {action.value}")
        return " ".join(parts)
