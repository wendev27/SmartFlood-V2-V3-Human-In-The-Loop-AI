"""
AHP-style vulnerability scoring for SmartFlood relief prioritization.

Seven factors (weights sum to 100%, deterministic, explainable — no ML):
PWD, Infant, Elderly, Pregnant, 4Ps beneficiary, Lactating mother, Solo parent.

Each factor has a documented rationale tied to evacuation difficulty, health risk,
or socioeconomic stress during floods.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class AHPService:
    """
    Weighted vulnerability model (transparent linear aggregation).
    Factor scores are in [0, 1]; priority_score = sum(weight_i * score_i) in [0, 1].
    """

    # Weights sum to 1.0 (100 %)
    WEIGHTS: Dict[str, float] = {
        "infant": 0.22,
        "elderly": 0.20,
        "pwd": 0.18,
        "pregnant": 0.12,
        "lactating": 0.10,
        "solo_parent": 0.10,
        "four_ps": 0.08,
    }

    FACTOR_RATIONALE: Dict[str, str] = {
        "infant": (
            "Infants cannot self-evacuate, are sensitive to hypothermia/contamination, "
            "and need caregivers — flood exposure sharply increases morbidity risk."
        ),
        "elderly": (
            "Older adults often have reduced mobility, chronic illness, and slower reaction time, "
            "making wading, climbing, and shelter transitions hazardous."
        ),
        "pwd": (
            "Persons with disabilities may rely on assistive devices, accessible routes, or carers; "
            "flood debris and uneven footing raise injury and entrapment risk."
        ),
        "pregnant": (
            "Pregnancy increases physical strain during movement, needs continuity of antenatal care, "
            "and complications can escalate without timely medical access."
        ),
        "lactating": (
            "Lactating mothers need nutrition, hydration, and privacy for infant feeding; "
            "displacement disrupts breastfeeding and infant energy intake."
        ),
        "solo_parent": (
            "Solo parents simultaneously supervise children and carry belongings; "
            "single-caregiver households bottleneck evacuation and queueing."
        ),
        "four_ps": (
            "4Ps households often have tighter budgets and fewer transport assets, "
            "delaying self-evacuation and increasing dependence on relief logistics."
        ),
    }

    NORMALIZATION_BASE = 5

    @classmethod
    def calculate_priority(
        cls,
        elderly_count: int = 0,
        infant_count: int = 0,
        pregnant_count: int = 0,
        pwd_count: int = 0,
        four_ps_count: int = 0,
        lactating_count: int = 0,
        solo_parent_count: int = 0,
        total_residents: int = 0,
    ) -> Dict[str, Any]:
        elderly_count = max(0, int(elderly_count))
        infant_count = max(0, int(infant_count))
        pregnant_count = max(0, int(pregnant_count))
        pwd_count = max(0, int(pwd_count))
        four_ps_count = max(0, int(four_ps_count))
        lactating_count = max(0, int(lactating_count))
        solo_parent_count = max(0, int(solo_parent_count))

        if total_residents <= 0:
            total_residents = max(
                1,
                elderly_count
                + infant_count
                + pregnant_count
                + pwd_count
                + four_ps_count
                + lactating_count
                + solo_parent_count,
            )

        scores = {
            "elderly": cls._calculate_factor_score(elderly_count, total_residents, "elderly"),
            "infant": cls._calculate_factor_score(infant_count, total_residents, "infant"),
            "pregnant": cls._calculate_factor_score(pregnant_count, total_residents, "pregnant"),
            "pwd": cls._calculate_factor_score(pwd_count, total_residents, "pwd"),
            "four_ps": cls._calculate_factor_score(four_ps_count, total_residents, "four_ps"),
            "lactating": cls._calculate_factor_score(lactating_count, total_residents, "lactating"),
            "solo_parent": cls._calculate_factor_score(solo_parent_count, total_residents, "solo_parent"),
        }

        weighted = {k: round(scores[k] * cls.WEIGHTS[k], 6) for k in cls.WEIGHTS}
        priority_score = round(sum(weighted.values()), 6)
        priority_score = max(0.0, min(1.0, priority_score))

        vulnerability_factors = cls._format_factors(
            elderly_count,
            infant_count,
            pregnant_count,
            pwd_count,
            four_ps_count,
            lactating_count,
            solo_parent_count,
        )

        weights_percent = {k: round(v * 100.0, 2) for k, v in cls.WEIGHTS.items()}

        explanation = cls._generate_explanation(
            priority_score,
            vulnerability_factors,
            weighted,
            scores,
        )

        breakdown_lines = cls._breakdown_lines(scores, weighted, weights_percent)

        logger.info(
            "AHP priority=%.3f factors=%s",
            priority_score,
            vulnerability_factors or ["none"],
        )

        return {
            "priority_score": priority_score,
            "sub_scores": {f"{k}_score": scores[k] for k in scores},
            "weighted_contributions": weighted,
            "weights_percent": weights_percent,
            "factor_rationale": dict(cls.FACTOR_RATIONALE),
            "breakdown_lines": breakdown_lines,
            "explanation": explanation,
            "vulnerability_factors": vulnerability_factors,
            "household_composition": {
                "elderly": elderly_count,
                "infant": infant_count,
                "pregnant": pregnant_count,
                "pwd": pwd_count,
                "four_ps": four_ps_count,
                "lactating": lactating_count,
                "solo_parent": solo_parent_count,
                "total_residents": total_residents,
            },
        }

    @staticmethod
    def _format_factors(
        elderly: int,
        infant: int,
        pregnant: int,
        pwd: int,
        four_ps: int,
        lactating: int,
        solo_parent: int,
    ) -> List[str]:
        out: List[str] = []
        if pwd:
            out.append(f"PWD ({pwd})")
        if infant:
            out.append(f"Infant ({infant})")
        if elderly:
            out.append(f"Elderly ({elderly})")
        if pregnant:
            out.append(f"Pregnant ({pregnant})")
        if four_ps:
            out.append(f"4Ps beneficiary ({four_ps})")
        if lactating:
            out.append(f"Lactating mother ({lactating})")
        if solo_parent:
            out.append(f"Solo parent ({solo_parent})")
        return out

    @classmethod
    def _calculate_factor_score(cls, count: int, total_residents: int, factor_type: str) -> float:
        if total_residents <= 0:
            return 0.0
        proportion = min(1.0, count / float(total_residents))

        # Bounded marginal impact per category (deterministic)
        multipliers = {
            "infant": 3.0,
            "elderly": 2.5,
            "pwd": 2.4,
            "pregnant": 1.6,
            "lactating": 1.7,
            "solo_parent": 1.8,
            "four_ps": 1.5,
        }
        m = multipliers.get(factor_type, 1.5)
        return max(0.0, min(1.0, proportion * m))

    @classmethod
    def _breakdown_lines(
        cls,
        scores: Dict[str, float],
        weighted: Dict[str, float],
        weights_percent: Dict[str, float],
    ) -> List[str]:
        lines = []
        for key in cls.WEIGHTS:
            pct = weights_percent[key]
            lines.append(
                f"{key}: weight {pct:.2f}% × factor {scores[key]:.3f} "
                f"→ contribution {weighted[key]:.4f} — {cls.FACTOR_RATIONALE[key]}"
            )
        return lines

    @classmethod
    def _generate_explanation(
        cls,
        priority_score: float,
        vulnerability_factors: List[str],
        weighted: Dict[str, float],
        scores: Dict[str, float],
    ) -> str:
        pct = int(round(priority_score * 100))
        parts = [
            f"Household / barangay vulnerability index: {pct}/100 (transparent weighted sum).",
        ]
        if not vulnerability_factors:
            parts.append("No tagged vulnerability factors in the registry for this query.")
        else:
            parts.append(f"Tagged vulnerable members: {', '.join(vulnerability_factors)}.")
        top = sorted(weighted.items(), key=lambda kv: kv[1], reverse=True)[:3]
        if top and top[0][1] > 0:
            parts.append(
                "Largest weighted drivers: "
                + ", ".join(f"{k} ({v:.3f})" for k, v in top if v > 0)
                + "."
            )
        if priority_score < 0.2:
            lvl = "low relief priority"
        elif priority_score < 0.4:
            lvl = "moderate relief priority"
        elif priority_score < 0.65:
            lvl = "high relief priority"
        else:
            lvl = "very high relief priority"
        parts.append(f"Relief band: {lvl}.")
        return " ".join(parts)


__all__ = ["AHPService"]
