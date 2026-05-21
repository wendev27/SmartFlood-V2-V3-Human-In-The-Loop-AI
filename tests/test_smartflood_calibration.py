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
    """Official hazard bands (depth in cm, stable, no rain unless noted)."""

    @pytest.mark.parametrize(
        "cm,expected_risk,descriptor_substr,depth_band",
        [
            (0, RiskLevel.LOW, "SAFE", "SAFE"),
            (9, RiskLevel.LOW, "SAFE", "SAFE"),
            (20, RiskLevel.LOW, "LOW HAZARD (YELLOW)", "LOW"),
            (33, RiskLevel.LOW, "LOW HAZARD (YELLOW)", "LOW"),
            (50, RiskLevel.LOW, "LOW HAZARD (YELLOW)", "LOW"),
            (51, RiskLevel.MEDIUM, "MEDIUM HAZARD (ORANGE)", "MEDIUM"),
            (80, RiskLevel.MEDIUM, "MEDIUM HAZARD (ORANGE)", "MEDIUM"),
            (89, RiskLevel.MEDIUM, "MEDIUM HAZARD (ORANGE)", "MEDIUM"),
            (150, RiskLevel.MEDIUM, "MEDIUM HAZARD (ORANGE)", "MEDIUM"),
            (151, RiskLevel.CRITICAL, "HIGH HAZARD (RED)", "HIGH"),
            (170, RiskLevel.CRITICAL, "HIGH HAZARD (RED)", "HIGH"),
            (180, RiskLevel.CRITICAL, "HIGH HAZARD (RED)", "HIGH"),
        ],
    )
    def test_official_depth_examples(
        self, cm: int, expected_risk: RiskLevel, descriptor_substr: str, depth_band: str
    ) -> None:
        r = FuzzyLogicService.assess_risk(float(cm), float(cm), "stable", 0.0)
        assert r["risk_level"] == expected_risk
        assert descriptor_substr in r["hazard_descriptor"]
        assert r["depth_hazard_band"] == depth_band

    def test_zero_depth_never_critical_even_with_severe_rain(self) -> None:
        r = FuzzyLogicService.assess_risk(0.0, 0.0, "rising", 200.0)
        assert r["risk_level"] in (RiskLevel.LOW, RiskLevel.MEDIUM)
        assert r["risk_level"] != RiskLevel.CRITICAL

    def test_rainfall_severe_escalates_medium_depth(self) -> None:
        r = FuzzyLogicService.assess_risk(89.0, 89.0, "stable", 160.0)
        assert r["rainfall_severity"] == "SEVERE"
        assert r["risk_level"] in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_rainfall_moderate_band(self) -> None:
        r = FuzzyLogicService.assess_risk(40.0, 40.0, "stable", 80.0)
        assert r["rainfall_severity"] == "MODERATE"


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
    def test_critical_hazard_triggers_evacuation_and_relief(
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
        assert out["risk_level"] == RiskLevel.CRITICAL
        assert RecommendedAction.FULL_EVACUATION in actions
        assert RecommendedAction.IMMEDIATE_RELIEF in actions
        assert out["fuzzy_assessment"] is not None
        assert out["explainability"] is not None

    def test_low_hazard_prepares_response_teams(self, mock_mongo, mock_supa) -> None:
        mock_mongo.return_value = {
            "avg_water_level": 33.0,
            "max_water_level": 33.0,
            "trend": "stable",
            "rainfall_intensity_mm": 10.0,
            "readings_count": 2,
        }
        mock_supa.return_value = {
            "elderly_count": 0,
            "infant_count": 0,
            "pregnant_count": 0,
            "pwd_count": 0,
            "four_ps_count": 0,
            "lactating_count": 0,
            "solo_parent_count": 0,
            "total_residents": 5,
        }
        out = DecisionService.make_decision(1)
        assert out["risk_level"] == RiskLevel.LOW
        actions = [s["action"] for s in out["suggestions"]]
        assert RecommendedAction.PREPARE in actions

    def test_medium_hazard_stages_evacuation_resources(self, mock_mongo, mock_supa) -> None:
        mock_mongo.return_value = {
            "avg_water_level": 89.0,
            "max_water_level": 89.0,
            "trend": "stable",
            "rainfall_intensity_mm": 30.0,
            "readings_count": 2,
        }
        mock_supa.return_value = {
            "elderly_count": 0,
            "infant_count": 0,
            "pregnant_count": 0,
            "pwd_count": 0,
            "four_ps_count": 0,
            "lactating_count": 0,
            "solo_parent_count": 0,
            "total_residents": 5,
        }
        out = DecisionService.make_decision(2)
        assert out["risk_level"] == RiskLevel.MEDIUM
        actions = [s["action"] for s in out["suggestions"]]
        assert (
            RecommendedAction.PREPARE_ADDITIONAL_RESOURCES in actions
            or RecommendedAction.PARTIAL_EVACUATION in actions
            or RecommendedAction.PREPARE_FOOD_PACKS in actions
        )
