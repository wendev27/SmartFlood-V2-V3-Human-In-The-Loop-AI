"""
Fuzzy Logic service for SmartFlood flood risk assessment (rule-based, explainable).

Official calibration (project manager):
- Flood depth in MongoDB: water_level_cm (centimeters); internal hazard bands use meters.
- LOW HAZARD (YELLOW): 10–50 cm (0.10–0.50 m)
- MEDIUM HAZARD (ORANGE): 51–150 cm (0.51–1.50 m)
- HIGH HAZARD (RED): > 150 cm (> 1.50 m)
- Rainfall IDF design reference: 243.100 mm
- Rainfall contribution: 0–50 mm LOW, 51–150 mm MODERATE, > 150 mm SEVERE
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.models.schemas import RiskLevel

logger = logging.getLogger(__name__)


class FuzzyLogicService:
    """
    Official SmartFlood hazard bands with fuzzy boundary softening,
    rainfall severity fusion, and explainable reasoning steps.
    """

    DESIGN_RAINFALL_MM = 243.100
    RETURN_PERIOD_YEARS = 5
    ANNUAL_EXCEEDANCE_PROBABILITY = 0.20

    # Depth bands (centimeters) — official thresholds
    SAFE_MAX_CM = 10.0
    LOW_MIN_CM = 10.0
    LOW_MAX_CM = 50.0
    MED_MIN_CM = 51.0
    MED_MAX_CM = 150.0
    HIGH_ABOVE_CM = 150.0

    # Depth bands (meters) — derived for documentation / reasoning
    HAZARD_LOW_MIN_M = LOW_MIN_CM / 100.0
    HAZARD_LOW_MAX_M = LOW_MAX_CM / 100.0
    HAZARD_MED_MIN_M = MED_MIN_CM / 100.0
    HAZARD_MED_MAX_M = MED_MAX_CM / 100.0
    HAZARD_HIGH_ABOVE_M = HIGH_ABOVE_CM / 100.0
    SAFE_DEPTH_CEILING_M = SAFE_MAX_CM / 100.0

    # Rainfall severity bands (mm)
    RAIN_LOW_MAX_MM = 50.0
    RAIN_MODERATE_MAX_MM = 150.0

    _RISK_ORDER: Tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    @classmethod
    def assess_risk(
        cls,
        avg_water_level: float,
        max_water_level: float,
        trend: str,
        rainfall_intensity_mm: float | None = None,
    ) -> Dict[str, Any]:
        """
        Assess flood risk using official depth + rainfall criteria.

        Args:
            avg_water_level: Average water level in cm
            max_water_level: Maximum water level in cm (recent window)
            trend: rising | falling | stable
            rainfall_intensity_mm: Recent rainfall intensity (mm); optional
        """
        avg_water_level = max(0.0, float(avg_water_level))
        max_water_level = max(0.0, float(max_water_level))
        trend_l = str(trend or "stable").lower()
        if trend_l not in ("rising", "falling", "stable"):
            trend_l = "stable"

        rain = 0.0 if rainfall_intensity_mm is None else max(0.0, float(rainfall_intensity_mm))

        d_avg_m = cls._cm_to_m(avg_water_level)
        d_max_m = cls._cm_to_m(max_water_level)
        peak_cm = max(avg_water_level, max_water_level)

        depth_hazard = cls._official_depth_hazard_cm(peak_cm)
        rain_severity = cls._rainfall_severity(rain)

        mu_depth = cls._memberships_from_depth_hazard(depth_hazard, peak_cm)
        mu_rain = cls._memberships_from_rainfall(rain, rain_severity)
        mu_depth = cls._fuzzy_or(mu_depth, cls._memberships_from_depth_hazard(
            cls._official_depth_hazard_cm(max_water_level), max_water_level
        ), spike_weight=0.90)
        mu_fused = cls._fuse_depth_and_rainfall(mu_depth, mu_rain, rain_severity)
        mu_after_trend = cls._apply_trend(mu_fused, trend_l)

        probs = cls._normalize_distribution(mu_after_trend)
        risk_key = cls._depth_rain_to_engine_risk(depth_hazard, rain_severity, trend_l)
        # Posterior should not undercut official combined classification
        if cls._risk_rank(risk_key) > cls._risk_rank(max(probs, key=probs.get)):
            risk_key = risk_key

        risk_level = RiskLevel[risk_key]

        forced_dry_low = peak_cm < cls.SAFE_MAX_CM - 1e-9 and avg_water_level < cls.SAFE_MAX_CM - 1e-9
        if forced_dry_low:
            risk_key = "LOW"
            risk_level = RiskLevel.LOW
            depth_hazard = "SAFE"
            probs = cls._normalize_distribution(
                {"LOW": 0.92, "MEDIUM": 0.05, "HIGH": 0.02, "CRITICAL": 0.01}
            )

        confidence = cls._confidence_from_distribution(
            probs, trend_l, rain, d_avg_m, d_max_m, depth_hazard, rain_severity
        )
        if forced_dry_low:
            confidence = max(confidence, 0.82)

        hazard_descriptor = cls._hazard_descriptor(depth_hazard, risk_key)
        reasoning_steps = cls._build_reasoning_steps(
            avg_water_level,
            max_water_level,
            d_avg_m,
            d_max_m,
            peak_cm,
            depth_hazard,
            rain_severity,
            trend_l,
            rain,
            mu_fused,
            probs,
            risk_key,
            hazard_descriptor,
            forced_dry_low=forced_dry_low,
        )
        explanation = cls._generate_explanation(
            avg_water_level,
            max_water_level,
            trend_l,
            rain,
            risk_key,
            confidence,
            hazard_descriptor,
            depth_hazard,
            rain_severity,
            probs,
        )

        logger.info(
            "Risk assessment: level=%s depth_hazard=%s rain=%s conf=%.2f peak_cm=%.1f",
            risk_key,
            depth_hazard,
            rain_severity,
            confidence,
            peak_cm,
        )

        return {
            "risk_level": risk_level,
            "confidence_score": confidence,
            "explanation": explanation,
            "membership_scores": {k: round(probs.get(k, 0.0), 4) for k in cls._RISK_ORDER},
            "avg_water_level": avg_water_level,
            "max_water_level": max_water_level,
            "trend": trend_l,
            "rainfall_intensity_mm": rain,
            "depth_avg_m": round(d_avg_m, 4),
            "depth_max_m": round(d_max_m, 4),
            "hazard_descriptor": hazard_descriptor,
            "depth_hazard_band": depth_hazard,
            "rainfall_severity": rain_severity,
            "reasoning_steps": reasoning_steps,
            "engineering_context": {
                "design_rainfall_mm": cls.DESIGN_RAINFALL_MM,
                "return_period_years": cls.RETURN_PERIOD_YEARS,
                "annual_exceedance_probability": cls.ANNUAL_EXCEEDANCE_PROBABILITY,
                "hazard_bands_cm": {
                    "safe_below_cm": cls.SAFE_MAX_CM,
                    "low_yellow_cm": [cls.LOW_MIN_CM, cls.LOW_MAX_CM],
                    "medium_orange_cm": [cls.MED_MIN_CM, cls.MED_MAX_CM],
                    "high_red_above_cm": cls.HIGH_ABOVE_CM,
                },
                "rainfall_bands_mm": {
                    "low": [0, cls.RAIN_LOW_MAX_MM],
                    "moderate": [cls.RAIN_LOW_MAX_MM + 1, cls.RAIN_MODERATE_MAX_MM],
                    "severe_above_mm": cls.RAIN_MODERATE_MAX_MM,
                },
            },
        }

    @staticmethod
    def _cm_to_m(cm: float) -> float:
        return cm / 100.0

    @classmethod
    def _official_depth_hazard_cm(cls, peak_cm: float) -> str:
        """Crisp official flood hazard from peak depth (cm)."""
        if peak_cm < cls.SAFE_MAX_CM:
            return "SAFE"
        if peak_cm <= cls.LOW_MAX_CM:
            return "LOW"
        if peak_cm <= cls.MED_MAX_CM:
            return "MEDIUM"
        return "HIGH"

    @classmethod
    def _rainfall_severity(cls, rainfall_mm: float) -> str:
        if rainfall_mm <= cls.RAIN_LOW_MAX_MM:
            return "LOW"
        if rainfall_mm <= cls.RAIN_MODERATE_MAX_MM:
            return "MODERATE"
        return "SEVERE"

    @classmethod
    def _risk_rank(cls, key: str) -> int:
        try:
            return cls._RISK_ORDER.index(key)
        except ValueError:
            return 0

    @classmethod
    def _bump_risk(cls, key: str, steps: int = 1) -> str:
        idx = min(len(cls._RISK_ORDER) - 1, cls._risk_rank(key) + steps)
        return cls._RISK_ORDER[idx]

    @classmethod
    def _depth_rain_to_engine_risk(
        cls, depth_hazard: str, rain_severity: str, trend: str
    ) -> str:
        """Map official depth + rainfall + trend to engine risk class."""
        if depth_hazard == "SAFE":
            base = "LOW"
        elif depth_hazard == "LOW":
            base = "LOW"
        elif depth_hazard == "MEDIUM":
            base = "MEDIUM"
        else:
            base = "CRITICAL"

        if rain_severity == "MODERATE":
            base = cls._bump_risk(base, 1)
        elif rain_severity == "SEVERE":
            base = cls._bump_risk(base, 2)

        if trend == "rising" and base != "CRITICAL":
            base = cls._bump_risk(base, 1)
        elif trend == "falling" and base != "LOW":
            base = cls._RISK_ORDER[max(0, cls._risk_rank(base) - 1)]

        return base

    @classmethod
    def _memberships_from_depth_hazard(cls, depth_hazard: str, peak_cm: float) -> Dict[str, float]:
        """Soft memberships anchored on official depth band."""
        soft = 2.0  # cm fuzzy shoulder at boundaries
        mu = {"LOW": 0.0, "MEDIUM": 0.0, "HIGH": 0.0, "CRITICAL": 0.0}

        if depth_hazard == "SAFE":
            mu["LOW"] = 1.0
        elif depth_hazard == "LOW":
            mu["LOW"] = 1.0
            if peak_cm > cls.LOW_MAX_CM - soft:
                mu["MEDIUM"] = min(1.0, (peak_cm - (cls.LOW_MAX_CM - soft)) / (2 * soft))
                mu["LOW"] = max(0.0, 1.0 - mu["MEDIUM"])
        elif depth_hazard == "MEDIUM":
            mu["MEDIUM"] = 1.0
            if peak_cm < cls.MED_MIN_CM + soft:
                mu["LOW"] = min(1.0, (cls.MED_MIN_CM + soft - peak_cm) / (2 * soft))
                mu["MEDIUM"] = max(0.0, 1.0 - mu["LOW"])
            if peak_cm > cls.MED_MAX_CM - soft:
                mu["HIGH"] = min(1.0, (peak_cm - (cls.MED_MAX_CM - soft)) / (2 * soft))
                mu["MEDIUM"] = max(0.0, mu["MEDIUM"] - mu["HIGH"] * 0.5)
        else:
            mu["CRITICAL"] = 1.0
            if peak_cm < cls.HIGH_ABOVE_CM + soft:
                mu["HIGH"] = min(1.0, (cls.HIGH_ABOVE_CM + soft - peak_cm) / (2 * soft))
                mu["CRITICAL"] = max(0.0, 1.0 - mu["HIGH"])

        return mu

    @classmethod
    def _memberships_from_rainfall(cls, rainfall_mm: float, severity: str) -> Dict[str, float]:
        mu = {"LOW": 0.0, "MEDIUM": 0.0, "HIGH": 0.0, "CRITICAL": 0.0}
        if severity == "LOW":
            mu["LOW"] = 1.0
        elif severity == "MODERATE":
            mu["MEDIUM"] = 0.85
            mu["HIGH"] = 0.25
        else:
            mu["HIGH"] = 0.75
            mu["CRITICAL"] = 0.9
        ratio = min(1.0, rainfall_mm / cls.DESIGN_RAINFALL_MM) if cls.DESIGN_RAINFALL_MM > 0 else 0.0
        mu["CRITICAL"] = max(mu["CRITICAL"], ratio * 0.35)
        return mu

    @classmethod
    def _fuse_depth_and_rainfall(
        cls,
        mu_depth: Dict[str, float],
        mu_rain: Dict[str, float],
        rain_severity: str,
    ) -> Dict[str, float]:
        out: Dict[str, float] = {}
        rain_weight = 0.45 if rain_severity == "MODERATE" else (0.62 if rain_severity == "SEVERE" else 0.18)
        for k in cls._RISK_ORDER:
            d = mu_depth.get(k, 0.0)
            r = mu_rain.get(k, 0.0)
            combined = (1.0 - rain_weight) * d + rain_weight * max(d, r)
            out[k] = min(1.0, combined)
        return out

    @staticmethod
    def _fuzzy_or(
        a: Dict[str, float],
        b: Dict[str, float],
        spike_weight: float = 0.88,
    ) -> Dict[str, float]:
        keys = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        out: Dict[str, float] = {}
        for k in keys:
            va, vb = a.get(k, 0.0), b.get(k, 0.0) * spike_weight
            out[k] = 1.0 - (1.0 - min(1.0, va)) * (1.0 - min(1.0, vb))
        return out

    @staticmethod
    def _apply_trend(mu: Dict[str, float], trend: str) -> Dict[str, float]:
        out = {k: mu.get(k, 0.0) for k in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
        if trend == "rising":
            out["LOW"] *= 0.88
            out["MEDIUM"] *= 1.08
            out["HIGH"] *= 1.14
            out["CRITICAL"] *= 1.22
        elif trend == "falling":
            out["LOW"] *= 1.10
            out["MEDIUM"] *= 0.95
            out["HIGH"] *= 0.88
            out["CRITICAL"] *= 0.80
        return out

    @staticmethod
    def _normalize_distribution(mu: Dict[str, float]) -> Dict[str, float]:
        keys = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        s = sum(max(0.0, mu.get(k, 0.0)) for k in keys)
        if s <= 1e-12:
            return {"LOW": 1.0, "MEDIUM": 0.0, "HIGH": 0.0, "CRITICAL": 0.0}
        return {k: max(0.0, mu.get(k, 0.0)) / s for k in keys}

    @classmethod
    def _confidence_from_distribution(
        cls,
        probs: Dict[str, float],
        trend: str,
        rainfall_mm: float,
        d_avg_m: float,
        d_max_m: float,
        depth_hazard: str,
        rain_severity: str,
    ) -> float:
        ordered = sorted((probs.get(k, 0.0) for k in cls._RISK_ORDER), reverse=True)
        top = ordered[0]
        second = ordered[1] if len(ordered) > 1 else 0.0
        margin = top - second

        base = 0.52 * top + 0.38 * min(1.0, margin * 4.0) + 0.10
        if depth_hazard in ("MEDIUM", "HIGH"):
            base += 0.04
        if rain_severity == "SEVERE":
            base += 0.03
        if trend == "stable":
            base += 0.02
        if abs(d_max_m - d_avg_m) > 0.25:
            base -= 0.04
        if rainfall_mm > cls.DESIGN_RAINFALL_MM:
            base -= 0.02
        return max(0.0, min(1.0, base))

    @classmethod
    def _hazard_descriptor(cls, depth_hazard: str, risk_key: str) -> str:
        if risk_key == "CRITICAL" or depth_hazard == "HIGH":
            return "HIGH HAZARD (RED) / CRITICAL"
        if depth_hazard == "MEDIUM":
            return "MEDIUM HAZARD (ORANGE)"
        if depth_hazard == "LOW":
            return "LOW HAZARD (YELLOW)"
        return "SAFE / LOW"

    @classmethod
    def _build_reasoning_steps(
        cls,
        avg_cm: float,
        max_cm: float,
        d_avg_m: float,
        d_max_m: float,
        peak_cm: float,
        depth_hazard: str,
        rain_severity: str,
        trend: str,
        rain_mm: float,
        mu_fused: Dict[str, float],
        probs: Dict[str, float],
        risk_key: str,
        hazard_descriptor: str,
        forced_dry_low: bool,
    ) -> List[str]:
        steps = [
            (
                f"Sensor depth: average={avg_cm:.1f} cm ({d_avg_m:.3f} m), "
                f"peak={max_cm:.1f} cm ({d_max_m:.3f} m); governing peak={peak_cm:.1f} cm."
            ),
            (
                f"Official depth hazard band: {depth_hazard} "
                f"(YELLOW 10–50 cm, ORANGE 51–150 cm, RED >150 cm)."
            ),
            (
                f"Rainfall intensity={rain_mm:.1f} mm → severity {rain_severity} "
                f"(LOW ≤{cls.RAIN_LOW_MAX_MM:.0f}, MODERATE ≤{cls.RAIN_MODERATE_MAX_MM:.0f}, "
                f"SEVERE >{cls.RAIN_MODERATE_MAX_MM:.0f}); IDF design={cls.DESIGN_RAINFALL_MM} mm."
            ),
            (
                f"Fused memberships: LOW={mu_fused.get('LOW', 0):.3f}, MEDIUM={mu_fused.get('MEDIUM', 0):.3f}, "
                f"HIGH={mu_fused.get('HIGH', 0):.3f}, CRITICAL={mu_fused.get('CRITICAL', 0):.3f}."
            ),
            (
                f"Posterior: LOW={probs.get('LOW', 0):.3f}, MEDIUM={probs.get('MEDIUM', 0):.3f}, "
                f"HIGH={probs.get('HIGH', 0):.3f}, CRITICAL={probs.get('CRITICAL', 0):.3f} → {risk_key}."
            ),
            f"Public label: {hazard_descriptor}. Trend={trend} adjusts escalation.",
        ]
        if forced_dry_low:
            steps.append(
                f"Guardrail: depth below {cls.SAFE_MAX_CM:.0f} cm — classification capped at SAFE/LOW."
            )
        return steps

    @classmethod
    def _generate_explanation(
        cls,
        avg_cm: float,
        max_cm: float,
        trend: str,
        rain_mm: float,
        risk_key: str,
        confidence: float,
        hazard_descriptor: str,
        depth_hazard: str,
        rain_severity: str,
        probs: Dict[str, float],
    ) -> str:
        conf_pct = int(round(confidence * 100))
        return (
            f"SmartFlood fuzzy assessment: {hazard_descriptor} (engine class {risk_key}). "
            f"Official depth band {depth_hazard}; water average {avg_cm:.1f} cm, peak {max_cm:.1f} cm; "
            f"trend={trend}. Rainfall {rain_mm:.1f} mm ({rain_severity} severity vs IDF "
            f"{cls.DESIGN_RAINFALL_MM} mm). "
            f"Posterior LOW/MEDIUM/HIGH/CRITICAL = "
            f"{probs.get('LOW', 0):.0%}/{probs.get('MEDIUM', 0):.0%}/"
            f"{probs.get('HIGH', 0):.0%}/{probs.get('CRITICAL', 0):.0%}; confidence {conf_pct}%."
        )


__all__ = ["FuzzyLogicService"]
