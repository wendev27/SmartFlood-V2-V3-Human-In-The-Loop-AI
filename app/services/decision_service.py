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
from app.services.resource_recommendation_service import ResourceRecommendationService

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
                rainfall_intensity_mm=float(sensor_data.get("rainfall_intensity_mm") or 0.0),
            )

            household_data = SupabaseConnection.get_household_vulnerability(barangay_id)

            ahp_result = AHPService.calculate_priority(
                elderly_count=household_data["elderly_count"],
                infant_count=household_data["infant_count"],
                pregnant_count=household_data["pregnant_count"],
                pwd_count=household_data["pwd_count"],
                four_ps_count=household_data.get("four_ps_count", 0),
                lactating_count=household_data.get("lactating_count", 0),
                solo_parent_count=household_data.get("solo_parent_count", 0),
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

            fuzzy_assessment = cls._fuzzy_assessment_payload(fuzzy_result)
            ahp_breakdown = cls._ahp_breakdown_payload(ahp_result)
            explainability = cls._explainability_payload(
                fuzzy_result, ahp_result, suggestions
            )
            
            # New Operational Logistics Engine
            operational_outputs = ResourceRecommendationService.generate_recommendations(
                fuzzy_result=fuzzy_result,
                ahp_result=ahp_result,
                household_data=household_data,
                sensor_data=sensor_data,
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
                "fuzzy_assessment": fuzzy_assessment,
                "ahp_breakdown": ahp_breakdown,
                "explainability": explainability,
                "_metadata": {
                    "sensor_readings_count": sensor_data.get("readings_count", 0),
                    "total_residents": household_data.get("total_residents", 0),
                    "vulnerability_factors": ahp_result.get("vulnerability_factors", []),
                    "rainfall_intensity_mm": sensor_data.get("rainfall_intensity_mm", 0.0),
                },
                **operational_outputs
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
                "fuzzy_assessment": None,
                "ahp_breakdown": None,
                "explainability": None,
                "_metadata": {"error": str(e)},
                # Fallback operational fields
                "priority_level": "MEDIUM",
                "analysis_confidence": 30,
                "affected_families": 0,
                "affected_population": 0,
                "estimated_evacuation_population": 0,
                "recommended_items": [],
                "analysis_reason": [f"System error: {str(e)[:50]}..."],
                "operational_urgency_score": 50,
                "recommendation_status": "monitoring",
                "inventory_constraints": [],
                "adjusted_recommendations": False,
                "recommendation_source": ["error_fallback"],
                "operational_notes": ["System degraded. Operating in fallback mode."],
                "sensor_reliability": None
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
    def _fuzzy_assessment_payload(cls, fuzzy_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "hazard_descriptor": fuzzy_result.get("hazard_descriptor", ""),
            "risk_level": fuzzy_result["risk_level"],
            "depth_avg_m": float(fuzzy_result.get("depth_avg_m", 0.0)),
            "depth_max_m": float(fuzzy_result.get("depth_max_m", 0.0)),
            "trend": str(fuzzy_result.get("trend", "stable")),
            "rainfall_intensity_mm": float(fuzzy_result.get("rainfall_intensity_mm", 0.0)),
            "confidence_score": float(fuzzy_result.get("confidence_score", 0.0)),
            "membership_scores": dict(fuzzy_result.get("membership_scores") or {}),
            "reasoning_steps": list(fuzzy_result.get("reasoning_steps") or []),
        }

    @classmethod
    def _ahp_breakdown_payload(cls, ahp: Dict[str, Any]) -> Dict[str, Any]:
        subs = {k: float(v) for k, v in (ahp.get("sub_scores") or {}).items()}
        return {
            "priority_score": float(ahp.get("priority_score", 0.0)),
            "weights_percent": dict(ahp.get("weights_percent") or {}),
            "weighted_contributions": dict(ahp.get("weighted_contributions") or {}),
            "sub_scores": subs,
            "breakdown_lines": list(ahp.get("breakdown_lines") or []),
            "vulnerability_factors": list(ahp.get("vulnerability_factors") or []),
            "factor_rationale": dict(ahp.get("factor_rationale") or {}),
        }

    @classmethod
    def _explainability_payload(
        cls,
        fuzzy_result: Dict[str, Any],
        ahp_result: Dict[str, Any],
        suggestions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        risk = cls._risk_str(fuzzy_result)
        trend = str(fuzzy_result.get("trend", "stable"))
        rain = float(fuzzy_result.get("rainfall_intensity_mm") or 0.0)
        depth = float(fuzzy_result.get("depth_avg_m") or 0.0)
        pr = float(ahp_result.get("priority_score", 0.0))
        memberships = fuzzy_result.get("membership_scores") or {}
        steps = fuzzy_result.get("reasoning_steps") or []
        why_flood = (
            f"Hazard label «{fuzzy_result.get('hazard_descriptor', '')}» corresponds to fuzzy class {risk} "
            f"with average depth {depth:.2f} m, trend {trend}, rainfall {rain:.1f} mm, "
            f"and posterior weights {memberships}. "
            f"Key reasoning: {' | '.join(steps[:5])}"
        )
        lines = ahp_result.get("breakdown_lines") or []
        why_priority = f"{ahp_result.get('explanation', '')} Contribution audit: {'; '.join(lines[:5])}."
        top_explained: List[str] = []
        for s in suggestions[:5]:
            act = s["action"]
            av = act.value if hasattr(act, "value") else str(act)
            top_explained.append(
                f"Rank {s['priority_rank']} — {av}: {s.get('reason', '')}. "
                f"Drivers: hazard={risk}, trend={trend}, rain={rain:.1f} mm, vulnerability_index={pr:.2f}."
            )
        return {
            "why_flood_risk_classified": why_flood,
            "why_barangay_priority": why_priority,
            "top_recommendations_explained": top_explained,
        }

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
        depth_m = float(fuzzy_result.get("depth_max_m", 0.0) or fuzzy_result.get("depth_avg_m", 0.0))
        rain_mm = float(fuzzy_result.get("rainfall_intensity_mm", 0.0))
        design = FuzzyLogicService.DESIGN_RAINFALL_MM
        rain_ratio = rain_mm / design if design > 0 else 0.0
        rain_severe = rain_mm > FuzzyLogicService.RAIN_MODERATE_MAX_MM
        rain_moderate = (
            FuzzyLogicService.RAIN_LOW_MAX_MM < rain_mm <= FuzzyLogicService.RAIN_MODERATE_MAX_MM
        )
        rain_heavy = rain_severe or rain_moderate
        depth_hazard = str(fuzzy_result.get("depth_hazard_band", ""))
        catastrophic_depth = depth_m > FuzzyLogicService.HAZARD_HIGH_ABOVE_M
        high_hazard = risk in ("HIGH", "CRITICAL") or depth_hazard == "HIGH"

        high_p = priority >= cls.HIGH_PRIORITY_THRESHOLD
        med_p = priority >= cls.MEDIUM_PRIORITY_THRESHOLD
        rising = trend == "rising"
        falling = trend == "falling"

        raw: List[_RawSuggestion] = []

        def conf(base: float) -> float:
            return max(0.0, min(1.0, base))

        # --- Full evacuation (HIGH/CRITICAL hazard + demographics) ---
        if high_hazard and rising and high_p and (catastrophic_depth or rain_severe):
            raw.append(
                _RawSuggestion(
                    RecommendedAction.FULL_EVACUATION,
                    (
                        "Depth near or above official HIGH band with rising trend and concentrated "
                        "vulnerability; intense rainfall vs IDF design further stresses drainage — "
                        "area-wide evacuation is the realistic protective action"
                    ),
                    109.0,
                    conf(min(0.97, risk_conf + 0.14 * (0.5 + rain_ratio))),
                )
            )
        elif high_hazard and rising and med_p and catastrophic_depth:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.FULL_EVACUATION,
                    (
                        "Very deep flood stage with rising hydrograph; even moderate demographic "
                        "vulnerability cannot be mitigated in place — coordinate full evacuation corridors"
                    ),
                    104.0,
                    conf(risk_conf * 0.93 + priority * 0.05),
                )
            )

        # --- Immediate relief / rescue / medical (HIGH hazard → CRITICAL response) ---
        if high_hazard and high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.IMMEDIATE_RELIEF,
                    (
                        "HIGH/CRITICAL hazard with high vulnerability — immediate relief allocation "
                        "and emergency response activation required"
                    ),
                    108.0 if risk == "CRITICAL" else 100.0,
                    conf(min(0.97, risk_conf + 0.14)),
                )
            )
        elif high_hazard:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.IMMEDIATE_RELIEF,
                    (
                        "Official HIGH hazard (depth >150 cm) — immediate relief allocation "
                        "and emergency logistics even with lower recorded vulnerability"
                    ),
                    98.0 if risk == "CRITICAL" else 94.0,
                    conf(min(0.94, risk_conf + 0.10)),
                )
            )
        elif risk == "MEDIUM" and high_p and (rising or rain_severe):
            raw.append(
                _RawSuggestion(
                    RecommendedAction.IMMEDIATE_RELIEF,
                    (
                        "MEDIUM hazard with vulnerable residents and either rising water or rainfall "
                        "approaching design IDF — relief lead times are shrinking"
                    ),
                    93.0,
                    conf(risk_conf * 0.90 + priority * 0.08 + (0.04 if rain_heavy else 0.0)),
                )
            )
        elif risk == "MEDIUM" and high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.IMMEDIATE_RELIEF,
                    "Elevated flood risk with high household vulnerability warrants urgent relief",
                    90.0,
                    conf(risk_conf * 0.92 + priority * 0.08),
                )
            )

        if high_hazard:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.DEPLOY_RESCUE_TEAM,
                    (
                        "HIGH/CRITICAL hazard — deploy rescue teams; immediate evacuation "
                        f"corridors may be required (trend={trend}, rain={rain_mm:.1f} mm)"
                    ),
                    92.0 if risk == "CRITICAL" else 87.0,
                    conf(risk_conf * 0.90 + (0.08 if rising else 0.0) + (0.06 if rain_severe else 0.0)),
                )
            )
            raw.append(
                _RawSuggestion(
                    RecommendedAction.FULL_EVACUATION,
                    (
                        "Official RED-band flood depth — recommend immediate evacuation "
                        "coordination alongside relief staging"
                    ),
                    95.0 if catastrophic_depth else 88.0,
                    conf(risk_conf * 0.86 + (0.08 if rising else 0.0)),
                )
            )

        if high_p and risk not in ("LOW",):
            raw.append(
                _RawSuggestion(
                    RecommendedAction.SEND_MEDICAL_ASSISTANCE,
                    (
                        "Vulnerable household mix (infants, elderly, PWD, pregnancy, lactation, "
                        "solo parents, 4Ps) raises medical support priority alongside flood stress"
                    ),
                    79.0,
                    conf(0.72 * risk_conf + 0.28 * priority),
                )
            )

        if high_hazard and rising:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PARTIAL_EVACUATION,
                    "Rising hydrograph under HIGH/CRITICAL hazard — escalate toward full evacuation",
                    90.0 if risk == "CRITICAL" else 85.0,
                    conf(risk_conf * 0.88 + 0.08),
                )
            )
        elif risk == "MEDIUM" and rising:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PARTIAL_EVACUATION,
                    (
                        "MEDIUM hazard (51–150 cm) with rising trend — prepare evacuation centers "
                        "and staged movement for at-risk blocks"
                    ),
                    78.0,
                    conf(risk_conf * 0.84 + 0.06),
                )
            )

        if high_hazard and med_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE_FOOD_PACKS,
                    (
                        "HIGH hazard with moderate vulnerability — pre-position food packs for "
                        "shelters and in-place assistance until transport clears"
                    ),
                    70.0,
                    conf(risk_conf * 0.82 + priority * 0.1 + (0.03 if rain_heavy else 0.0)),
                )
            )
        elif risk == "MEDIUM" and (med_p or rain_moderate or rain_severe):
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE_FOOD_PACKS,
                    (
                        "MEDIUM hazard (ORANGE band) — preposition relief goods and food packs "
                        "for evacuation centers"
                    ),
                    62.0,
                    conf(0.58 * risk_conf + 0.25 * priority + (0.12 if rain_heavy else 0.0)),
                )
            )

        if risk == "MEDIUM":
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE_ADDITIONAL_RESOURCES,
                    (
                        "MEDIUM hazard — prepare evacuation centers and preposition relief goods "
                        f"(rainfall {rain_mm:.1f} mm, severity context vs IDF {design:.1f} mm)"
                    ),
                    68.0,
                    conf(risk_conf * 0.80 + (0.06 if rain_moderate else 0.0)),
                )
            )

        if high_hazard or (risk == "MEDIUM" and (rising or rain_heavy)):
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE_ADDITIONAL_RESOURCES,
                    (
                        "Escalation risk from hazard class, trend, or rainfall vs IDF reference — "
                        "pre-stage logistics (boats, trucks, fuel)"
                    ),
                    66.0 if rising or rain_heavy else 58.0,
                    conf(risk_conf * 0.78 + (0.08 if rising else 0.0) + (0.06 if rain_heavy else -0.05)),
                )
            )

        if risk == "MEDIUM" and med_p and not high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE,
                    (
                        "MEDIUM hazard (51–150 cm) — prepare evacuation centers and response teams; "
                        "verify routes and vulnerable household roster"
                    ),
                    60.0,
                    conf((risk_conf + priority) / 2 * 0.90),
                )
            )

        if risk == "MEDIUM" and not med_p and not rain_heavy:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.MONITOR,
                    (
                        "MEDIUM hazard with lower vulnerability index and rainfall below heavy IDF "
                        "fraction — intensify monitoring and field verification"
                    ),
                    48.0,
                    conf(risk_conf * 0.8),
                )
            )

        if risk == "LOW" and depth_hazard == "LOW":
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE,
                    (
                        "LOW hazard (YELLOW band, 10–50 cm) — prepare response teams and "
                        "preposition basic relief assets"
                    ),
                    52.0,
                    conf(risk_conf * 0.82 + priority * 0.08),
                )
            )

        if risk == "LOW" and high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.PREPARE,
                    (
                        "LOW/SAFE hydrology but concentrated vulnerability — prepare response teams "
                        "and keep transport on standby"
                    ),
                    48.0,
                    conf(risk_conf * 0.78 + priority * 0.15),
                )
            )

        if risk == "LOW" and depth_hazard in ("SAFE", "") and not high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.SAFE,
                    (
                        "Depth below 10 cm advisory threshold — monitor conditions; "
                        "routine readiness only"
                    ),
                    36.0,
                    conf(risk_conf * 0.88),
                )
            )
            raw.append(
                _RawSuggestion(
                    RecommendedAction.MONITOR,
                    "SAFE status — maintain sensor and field monitoring under changing rainfall",
                    34.0,
                    conf(0.58 + (0.05 if falling else 0.0)),
                )
            )
        elif risk == "LOW" and not high_p:
            raw.append(
                _RawSuggestion(
                    RecommendedAction.MONITOR,
                    (
                        "LOW hazard band with limited vulnerability — monitor conditions; "
                        "prepare response teams if rainfall intensifies"
                    ),
                    40.0,
                    conf(risk_conf * 0.80),
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

        if action == RecommendedAction.FULL_EVACUATION:
            parts.append(
                f"supports coordinated full evacuation as the top rule-based action "
                f"(confidence: {confidence_pct}%) because hazard, trend, and/or rainfall crossed "
                f"catastrophic staging thresholds with elevated vulnerability."
            )
        elif action == RecommendedAction.IMMEDIATE_RELIEF:
            parts.append(
                f"indicates immediate relief is the leading recommendation (confidence: {confidence_pct}%)."
            )
        elif action == RecommendedAction.PREPARE_FOOD_PACKS:
            parts.append(
                f"indicates food-pack staging and distribution readiness lead the response mix "
                f"(confidence: {confidence_pct}%)."
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

    @classmethod
    def make_city_wide_decision(cls) -> List[Dict[str, Any]]:
        """
        Evaluate all barangays and return a ranked list of priorities.
        """
        logger.info("Making city-wide decision")
        
        barangays = SupabaseConnection.get_all_barangays()
        if not barangays:
            logger.warning("No barangays found for city-wide analysis.")
            return []

        analysis_results = []
        for bg in barangays:
            bg_id = bg.get("id")
            if bg_id is None:
                continue
                
            try:
                bg_id_int = int(bg_id)
                decision = cls.make_decision(barangay_id=bg_id_int)
                
                # Format into CityWideAnalysisItem dict
                from app.models.schemas import RecommendationStatus
                
                item = {
                    "barangay_id": bg_id_int,
                    "barangay_name": bg.get("name", f"Barangay {bg_id_int}"),
                    "priority_level": decision.get("priority_level", "MEDIUM"),
                    "analysis_confidence": int(decision.get("analysis_confidence", 0)),
                    "operational_urgency_score": int(decision.get("operational_urgency_score", 0)),
                    "recommendation_status": decision.get("recommendation_status", RecommendationStatus.MONITORING),

                    "affected_population": int(decision.get("affected_population", 0)),
                    "affected_families": int(decision.get("affected_families", 0)),

                    "recommended_items": decision.get("recommended_items", []),
                    "analysis_reason": decision.get("analysis_reason", []),

                    "inventory_constraints": decision.get("inventory_constraints", []),
                    "sensor_reliability": decision.get("sensor_reliability"),

                    "operational_notes": decision.get("operational_notes", []),
                    "recommendation_source": decision.get("recommendation_source", []),
                    # We temporarily store priority_score and risk_level for sorting
                    "_priority_score": decision.get("priority_score", 0.0),
                    "_risk_level": decision.get("risk_level", RiskLevel.MEDIUM)
                }
                analysis_results.append(item)
            except Exception as e:
                logger.error(f"Error processing barangay {bg_id} for city-wide analysis: {e}")
                
        # Sort by: HIGH/CRITICAL risk first, then confidence score, then vulnerability (priority_score)
        def sort_key(item):
            risk = item["_risk_level"]
            risk_str = risk.value if hasattr(risk, "value") else str(risk)
            if risk_str == "CRITICAL":
                risk_val = 4
            elif risk_str == "HIGH":
                risk_val = 3
            elif risk_str == "MEDIUM":
                risk_val = 2
            else:
                risk_val = 1
                
            return (
                risk_val,
                item["analysis_confidence"],
                item["_priority_score"]
            )
            
        analysis_results.sort(key=sort_key, reverse=True)
        
        # Remove temporary sorting fields
        for item in analysis_results:
            item.pop("_priority_score", None)
            item.pop("_risk_level", None)
            
        return analysis_results
