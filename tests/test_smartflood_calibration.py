"""
Validation tests for SmartFlood fuzzy recalibration, AHP expansion, and decision wiring.
Run: pytest tests/test_smartflood_calibration.py -q
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.schemas import RecommendedAction, RiskLevel
from app.services.ahp_service import AHPService
from app.services.decision_service import DecisionService
from app.services.fuzzy_service import FuzzyLogicService


class TestFuzzyHazardCalibration:
    """Expected hazard labels from the user brief (depth in cm, stable, no rain)."""

    @pytest.mark.parametrize(
        "cm,expected_risk,descriptor_substr",
        [
            (0, RiskLevel.LOW, "SAFE / LOW"),
            (20, RiskLevel.LOW, "LOW HAZARD (YELLOW)"),  # 0.2 m
            (80, RiskLevel.MEDIUM, "MEDIUM HAZARD (ORANGE)"),  # 0.8 m
            (180, RiskLevel.HIGH, "HIGH HAZARD (RED)"),  # 1.8 m
        ],
    )
    def test_example_depths(self, cm: int, expected_risk: RiskLevel, descriptor_substr: str) -> None:
        r = FuzzyLogicService.assess_risk(float(cm), float(cm), "stable", 0.0)
        assert r["risk_level"] == expected_risk
        assert descriptor_substr in r["hazard_descriptor"]

    def test_zero_depth_never_high_even_with_rain(self) -> None:
        r = FuzzyLogicService.assess_risk(0.0, 0.0, "rising", FuzzyLogicService.DESIGN_RAINFALL_MM * 2)
        assert r["risk_level"] == RiskLevel.LOW
        assert "HIGH" not in r["hazard_descriptor"]


class TestAHPSevenFactors:
    def test_weights_sum_to_one(self) -> None:
        assert abs(sum(AHPService.WEIGHTS.values()) - 1.0) < 1e-9

    def test_higher_vulnerability_with_more_tags(self) -> None:
        base = AHPService.calculate_priority(
            elderly_count=0,
            infant_count=0,
            pregnant_count=0,
            pwd_count=0,
            four_ps_count=0,
            lactating_count=0,
            solo_parent_count=0,
            total_residents=10,
        )
        full = AHPService.calculate_priority(
            elderly_count=1,
            infant_count=1,
            pregnant_count=1,
            pwd_count=1,
            four_ps_count=1,
            lactating_count=1,
            solo_parent_count=1,
            total_residents=10,
        )
        assert full["priority_score"] > base["priority_score"]
        assert len(full["breakdown_lines"]) == 7
        assert "weighted_contributions" in full


@patch("app.services.decision_service.SupabaseConnection.get_household_vulnerability")
@patch("app.services.decision_service.MongoDBConnection.get_sensor_data")
class TestDecisionIntegration:
    def test_full_evacuation_ranked_when_catastrophic(
        self, mock_mongo, mock_supa
    ) -> None:
        mock_mongo.return_value = {
            "avg_water_level": 170.0,
            "max_water_level": 170.0,
            "trend": "rising",
            "rainfall_intensity_mm": 200.0,
            "readings_count": 3,
        }
        mock_supa.return_value = {
            "elderly_count": 3,
            "infant_count": 4,
            "pregnant_count": 2,
            "pwd_count": 3,
            "four_ps_count": 3,
            "lactating_count": 2,
            "solo_parent_count": 2,
            "total_residents": 8,
        }
        out = DecisionService.make_decision(99)
        actions = [s["action"] for s in out["suggestions"]]
        assert RecommendedAction.FULL_EVACUATION in actions
        assert out["fuzzy_assessment"] is not None
        assert out["ahp_breakdown"] is not None
        assert out["explainability"] is not None
