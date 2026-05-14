"""
Fuzzy Logic service for SmartFlood flood risk assessment (rule-based, explainable).

Engineering context (calibration):
- IDF design rainfall reference: 243.100 mm (used to scale rainfall intensity input).
- Annual exceedance for 5-year return period: 20% (1/5) — documented for transparency.

Hazard bands (flood depth, meters), aligned with official SmartFlood levels:
- Below 0.1 m: no advisory flood depth exceeded — treated as SAFE / LOW classification.
- LOW HAZARD (YELLOW): 0.1 m – 0.5 m
- MEDIUM HAZARD (ORANGE): 0.5 m – 1.5 m
- HIGH HAZARD (RED): above 1.5 m

Sensor inputs remain in centimeters for MongoDB compatibility (converted internally to meters).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.models.schemas import RiskLevel

logger = logging.getLogger(__name__)


class FuzzyLogicService:
    """
    Trapezoidal / piecewise-linear fuzzy memberships over water depth (m),
    fused with trend and rainfall intensity, with explainable reasoning.
    """

    # --- Flood engineering reference (documentation + rainfall scaling) ---
    DESIGN_RAINFALL_MM = 243.100
    RETURN_PERIOD_YEARS = 5
    ANNUAL_EXCEEDANCE_PROBABILITY = 0.20  # 1/5 per year for 5-year RP (communicated to operators)

    # Official hazard depth bands (meters)
    HAZARD_LOW_MIN_M = 0.1
    HAZARD_LOW_MAX_M = 0.5
    HAZARD_MED_MIN_M = 0.5
    HAZARD_MED_MAX_M = 1.5
    HAZARD_HIGH_ABOVE_M = 1.5

    # Historical / advisory “no flood stage” upper bound (m) — below this, never classify HIGH from depth alone
    SAFE_DEPTH_CEILING_M = 0.10

    @classmethod
    def assess_risk(
        cls,
        avg_water_level: float,
        max_water_level: float,
        trend: str,
        rainfall_intensity_mm: float | None = None,
    ) -> Dict[str, Any]:
        """
        Assess flood risk using fuzzy memberships (LOW / MEDIUM / HIGH).

        Args:
            avg_water_level: Average water level in cm
            max_water_level: Maximum water level in cm (recent window)
            trend: rising | falling | stable
            rainfall_intensity_mm: Recent rainfall intensity (mm); optional — if missing, treated as 0.0

        Returns:
            Dict including risk_level (RiskLevel), confidence_score, hazard_descriptor,
            membership_scores, reasoning_steps, and engineering_notes.
        """
        avg_water_level = max(0.0, float(avg_water_level))
        max_water_level = max(0.0, float(max_water_level))
        trend_l = str(trend or "stable").lower()
        if trend_l not in ("rising", "falling", "stable"):
            trend_l = "stable"

        rain = 0.0 if rainfall_intensity_mm is None else max(0.0, float(rainfall_intensity_mm))

        d_avg_m = cls._cm_to_m(avg_water_level)
        d_max_m = cls._cm_to_m(max_water_level)

        mu_avg = cls._base_memberships_depth(d_avg_m)
        mu_max = cls._base_memberships_depth(d_max_m)
        # Peak-aware fusion (fuzzy OR): recent spikes cannot be ignored, but 0 m spike with 0 avg stays safe
        mu_depth = cls._fuzzy_or(mu_avg, mu_max, spike_weight=0.88)

        mu_after_trend = cls._apply_trend(mu_depth, trend_l)
        mu_after_rain = cls._apply_rainfall(mu_after_trend, rain)

        probs = cls._normalize_distribution(mu_after_rain)
        risk_key = max(probs, key=probs.get)  # "LOW" | "MEDIUM" | "HIGH"
        risk_level = RiskLevel[risk_key]

        forced_dry_low = (
            d_avg_m <= cls.SAFE_DEPTH_CEILING_M + 1e-9 and d_max_m <= cls.SAFE_DEPTH_CEILING_M + 1e-9
        )
        # Never classify HIGH/MEDIUM from depth alone at dry stage (guards bad sensors / noise)
        if forced_dry_low:
            risk_key = "LOW"
            risk_level = RiskLevel.LOW
            probs = cls._normalize_distribution(
                {"LOW": probs["LOW"] + probs["MEDIUM"] + probs["HIGH"], "MEDIUM": 0.0, "HIGH": 0.0}
            )

        confidence = cls._confidence_from_distribution(probs, trend_l, rain, d_avg_m, d_max_m)
        if forced_dry_low:
            confidence = max(confidence, 0.82)

        hazard_descriptor = cls._hazard_descriptor(risk_key, d_avg_m, d_max_m)
        reasoning_steps = cls._build_reasoning_steps(
            d_avg_m,
            d_max_m,
            trend_l,
            rain,
            mu_depth,
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
            probs,
        )

        logger.info(
            "Risk assessment: level=%s conf=%.2f trend=%s rain=%.1fmm depth_avg_m=%.3f",
            risk_key,
            confidence,
            trend_l,
            rain,
            d_avg_m,
        )

        return {
            "risk_level": risk_level,
            "confidence_score": confidence,
            "explanation": explanation,
            "membership_scores": {k: round(v, 4) for k, v in probs.items()},
            "avg_water_level": avg_water_level,
            "max_water_level": max_water_level,
            "trend": trend_l,
            "rainfall_intensity_mm": rain,
            "depth_avg_m": round(d_avg_m, 4),
            "depth_max_m": round(d_max_m, 4),
            "hazard_descriptor": hazard_descriptor,
            "reasoning_steps": reasoning_steps,
            "engineering_context": {
                "design_rainfall_mm": cls.DESIGN_RAINFALL_MM,
                "return_period_years": cls.RETURN_PERIOD_YEARS,
                "annual_exceedance_probability": cls.ANNUAL_EXCEEDANCE_PROBABILITY,
                "hazard_bands_m": {
                    "low_yellow": [cls.HAZARD_LOW_MIN_M, cls.HAZARD_LOW_MAX_M],
                    "medium_orange": [cls.HAZARD_MED_MIN_M, cls.HAZARD_MED_MAX_M],
                    "high_red_above_m": cls.HAZARD_HIGH_ABOVE_M,
                },
            },
        }

    @staticmethod
    def _cm_to_m(cm: float) -> float:
        return cm / 100.0

    @classmethod
    def _mu_low_depth(cls, x: float) -> float:
        """High when depth is small; tapers through low-hazard yellow band."""
        if x < 0.0:
            return 0.0
        if x <= cls.SAFE_DEPTH_CEILING_M:
            return 1.0
        if x <= cls.HAZARD_LOW_MAX_M:
            # gentle decay across official LOW hazard band
            return max(0.0, 1.0 - (x - cls.SAFE_DEPTH_CEILING_M) / (cls.HAZARD_LOW_MAX_M - cls.SAFE_DEPTH_CEILING_M) * 0.35)
        if x <= 0.62:
            return max(0.0, 0.65 - (x - cls.HAZARD_LOW_MAX_M) / (0.62 - cls.HAZARD_LOW_MAX_M) * 0.65)
        return 0.0

    @classmethod
    def _mu_medium_depth(cls, x: float) -> float:
        if x <= 0.35:
            return 0.0
        if x <= cls.HAZARD_MED_MIN_M:
            return (x - 0.35) / (cls.HAZARD_MED_MIN_M - 0.35)
        if x <= 1.20:
            return 1.0
        if x <= 1.62:
            return max(0.0, (1.62 - x) / (1.62 - 1.20))
        return 0.0

    @classmethod
    def _mu_high_depth(cls, x: float) -> float:
        if x <= 1.18:
            return 0.0
        if x <= cls.HAZARD_HIGH_ABOVE_M:
            return (x - 1.18) / (cls.HAZARD_HIGH_ABOVE_M - 1.18)
        return 1.0

    @classmethod
    def _base_memberships_depth(cls, depth_m: float) -> Dict[str, float]:
        return {
            "LOW": cls._mu_low_depth(depth_m),
            "MEDIUM": cls._mu_medium_depth(depth_m),
            "HIGH": cls._mu_high_depth(depth_m),
        }

    @staticmethod
    def _fuzzy_or(
        a: Dict[str, float],
        b: Dict[str, float],
        spike_weight: float = 0.88,
    ) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for k in ("LOW", "MEDIUM", "HIGH"):
            va, vb = a[k], b[k] * spike_weight
            out[k] = 1.0 - (1.0 - min(1.0, va)) * (1.0 - min(1.0, vb))
        return out

    @staticmethod
    def _apply_trend(mu: Dict[str, float], trend: str) -> Dict[str, float]:
        out = dict(mu)
        if trend == "rising":
            out["LOW"] *= 0.92
            out["MEDIUM"] *= 1.06
            out["HIGH"] *= 1.18
        elif trend == "falling":
            out["LOW"] *= 1.08
            out["MEDIUM"] *= 0.97
            out["HIGH"] *= 0.86
        return out

    @classmethod
    def _apply_rainfall(cls, mu: Dict[str, float], rainfall_mm: float) -> Dict[str, float]:
        out = dict(mu)
        ratio = min(1.5, rainfall_mm / cls.DESIGN_RAINFALL_MM) if cls.DESIGN_RAINFALL_MM > 0 else 0.0
        out["LOW"] *= max(0.55, 1.0 - 0.12 * ratio)
        out["MEDIUM"] *= 1.0 + 0.10 * ratio
        out["HIGH"] *= 1.0 + 0.22 * ratio
        return out

    @staticmethod
    def _normalize_distribution(mu: Dict[str, float]) -> Dict[str, float]:
        s = sum(max(0.0, v) for v in mu.values())
        if s <= 1e-12:
            return {"LOW": 1.0, "MEDIUM": 0.0, "HIGH": 0.0}
        return {k: max(0.0, v) / s for k, v in mu.items()}

    @classmethod
    def _confidence_from_distribution(
        cls,
        probs: Dict[str, float],
        trend: str,
        rainfall_mm: float,
        d_avg_m: float,
        d_max_m: float,
    ) -> float:
        """Deterministic confidence from winner strength, margin, and context."""
        ordered = sorted(probs.values(), reverse=True)
        top = ordered[0]
        second = ordered[1] if len(ordered) > 1 else 0.0
        margin = top - second

        base = 0.55 * top + 0.35 * min(1.0, margin * 4.0) + 0.10
        if trend == "stable":
            base += 0.02
        if abs(d_max_m - d_avg_m) > 0.08:
            base -= 0.03  # uncertainty when spike diverges
        if rainfall_mm > cls.DESIGN_RAINFALL_MM * 0.85:
            base -= 0.02
        return max(0.0, min(1.0, base))

    @classmethod
    def _hazard_descriptor(cls, risk_key: str, d_avg_m: float, d_max_m: float) -> str:
        d_show = max(d_avg_m, d_max_m)
        if risk_key == "HIGH":
            return "HIGH HAZARD (RED)"
        if risk_key == "MEDIUM":
            return "MEDIUM HAZARD (ORANGE)"
        # LOW risk_level: distinguish safe vs yellow band
        if d_show < cls.HAZARD_LOW_MIN_M - 1e-9:
            return "SAFE / LOW"
        if d_show <= cls.HAZARD_LOW_MAX_M + 1e-9:
            return "LOW HAZARD (YELLOW)"
        return "LOW (post-adjustment; depth below HIGH thresholds)"

    @classmethod
    def _build_reasoning_steps(
        cls,
        d_avg_m: float,
        d_max_m: float,
        trend: str,
        rain_mm: float,
        mu_depth: Dict[str, float],
        probs: Dict[str, float],
        risk_key: str,
        hazard_descriptor: str,
        forced_dry_low: bool,
    ) -> List[str]:
        steps = [
            f"Converted sensor depth: average={d_avg_m:.3f} m, recent peak={d_max_m:.3f} m.",
            (
                f"Depth memberships after peak fusion: LOW={mu_depth['LOW']:.3f}, "
                f"MEDIUM={mu_depth['MEDIUM']:.3f}, HIGH={mu_depth['HIGH']:.3f}."
            ),
            f"Trend={trend}: adjusts memberships toward worsening risk when rising, mitigating when falling.",
            (
                f"Rainfall intensity={rain_mm:.1f} mm vs design IDF {cls.DESIGN_RAINFALL_MM} mm "
                f"scales hydrologic stress in a bounded, rule-based way."
            ),
            (
                f"Normalized posterior: LOW={probs['LOW']:.3f}, MEDIUM={probs['MEDIUM']:.3f}, "
                f"HIGH={probs['HIGH']:.3f} → winner={risk_key}."
            ),
            f"Public hazard label: {hazard_descriptor}.",
            (
                f"Annual chance of exceeding a 5-year event in a year ≈ "
                f"{int(round(cls.ANNUAL_EXCEEDANCE_PROBABILITY * 100))}% (planning context only)."
            ),
        ]
        if forced_dry_low:
            steps.append(
                "Guardrail: at or below 0.10 m average and peak, classification is forced to LOW "
                "so sensors at dry stage never emit HIGH."
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
        probs: Dict[str, float],
    ) -> str:
        conf_pct = int(round(confidence * 100))
        parts = [
            f"SmartFlood fuzzy assessment: {hazard_descriptor} (engine class {risk_key}).",
            f"Water depth average {avg_cm/100:.2f} m, peak {max_cm/100:.2f} m; trend={trend}.",
            f"Rainfall intensity input {rain_mm:.1f} mm (design reference {cls.DESIGN_RAINFALL_MM} mm).",
            (
                f"Posterior weights LOW/MEDIUM/HIGH = "
                f"{probs['LOW']:.0%}/{probs['MEDIUM']:.0%}/{probs['HIGH']:.0%}; "
                f"confidence {conf_pct}%."
            ),
        ]
        return " ".join(parts)


__all__ = ["FuzzyLogicService"]
