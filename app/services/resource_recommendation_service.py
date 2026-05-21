"""
Resource Recommendation Service.
Evolves the AI into an Operational Disaster Logistics Intelligence Engine.
Handles deterministic resource estimation, multi-factor priority, and sensor reliability checks.
"""

from typing import Dict, Any, List
import logging
from app.config.operational_constants import (
    AVERAGE_HOUSEHOLD_SIZE,
    FOOD_PACK_SCALING,
    WATER_SCALING,
    MEDICINE_SCALING,
    HYGIENE_SCALING,
    BLANKET_SCALING,
    EVACUATION_PARTIAL_RATIO,
    EVACUATION_FULL_RATIO,
    URGENCY_CRITICAL_MIN,
    URGENCY_HIGH_MIN,
    URGENCY_MEDIUM_MIN,
)
from app.models.schemas import RiskLevel
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)


class ResourceRecommendationService:
    """
    Engine for generating operational logistics recommendations.
    Uses multi-factor logic to establish priority and calculates relief quantities.
    """

    @classmethod
    def generate_recommendations(
        cls,
        fuzzy_result: Dict[str, Any],
        ahp_result: Dict[str, Any],
        household_data: Dict[str, Any],
        sensor_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Main entrypoint for generating full operational recommendations.
        """
        # 1. Base Demographic Estimates
        total_residents = household_data.get("total_residents", 0)
        affected_families = max(1, total_residents // AVERAGE_HOUSEHOLD_SIZE)
        
        elderly = household_data.get("elderly_count", 0)
        infants = household_data.get("infant_count", 0)
        pregnant = household_data.get("pregnant_count", 0)
        pwd = household_data.get("pwd_count", 0)
        vulnerable_population = elderly + infants + pregnant + pwd

        risk_level = fuzzy_result.get("risk_level", RiskLevel.MEDIUM)
        if isinstance(risk_level, RiskLevel):
            risk_level_str = risk_level.value
        else:
            risk_level_str = str(risk_level)

        # 2. Sensor Reliability
        sensor_reliability = cls._calculate_sensor_reliability(sensor_data)
        
        # 3. Urgency and Priority (Multi-Factor)
        urgency_score, urgency_factors = cls._calculate_operational_urgency(
            fuzzy_result, ahp_result, sensor_reliability, vulnerable_population, total_residents
        )
        priority_level = cls._determine_priority_level(urgency_score, risk_level_str, ahp_result)

        # 4. Resource Estimation (Deterministic Rules)
        estimated_evacuation_population = cls._estimate_evacuation_population(
            total_residents, risk_level_str
        )
        
        ideal_items, resource_reasons = cls._estimate_resources(
            risk_level_str, 
            affected_families, 
            vulnerable_population, 
            estimated_evacuation_population,
            fuzzy_result
        )

        # 5. Inventory Checking
        adjusted_items, inventory_constraints, has_shortage = InventoryService.check_and_adjust_recommendations(
            ideal_items
        )

        # 6. Recommendation Status
        if has_shortage:
            recommendation_status = "resource_shortage"
        elif priority_level == "CRITICAL":
            recommendation_status = "critical"
        elif priority_level == "LOW":
            recommendation_status = "monitoring"
        else:
            recommendation_status = "stable"

        # 7. Analysis Reasons & Confidence
        analysis_confidence = int(fuzzy_result.get("confidence_score", 0.0) * 100)
        
        # Degrade confidence if sensors are offline
        if sensor_reliability["offline_sensors"] > 0:
            penalty = sensor_reliability["offline_sensors"] * 5
            analysis_confidence = max(0, analysis_confidence - penalty)

        analysis_reason = cls._build_analysis_reasons(
            fuzzy_result, ahp_result, urgency_factors, sensor_reliability
        )

        operational_notes = [
            f"Vulnerable Demographics Focus: {vulnerable_population} highly vulnerable individuals.",
            f"Evacuation Stress: Estimated {estimated_evacuation_population} individuals might require shelter."
        ]
        if has_shortage:
            operational_notes.append("Warehouse shortages detected. Adjusting recommendations to fit available supply.")

        return {
            "priority_level": priority_level,
            "analysis_confidence": analysis_confidence,
            "affected_families": affected_families,
            "affected_population": total_residents,
            "estimated_evacuation_population": estimated_evacuation_population,
            "recommended_items": adjusted_items,
            "analysis_reason": analysis_reason,
            "operational_urgency_score": urgency_score,
            "recommendation_status": recommendation_status,
            "inventory_constraints": inventory_constraints,
            "adjusted_recommendations": has_shortage,
            "recommendation_source": [
                "fuzzy_logic",
                "ahp_analysis",
                "resource_estimator",
                "inventory_checker"
            ],
            "operational_notes": operational_notes,
            "sensor_reliability": sensor_reliability,
            "_resource_reasons": resource_reasons
        }

    @classmethod
    def _calculate_sensor_reliability(cls, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes sensor data metadata to determine reliability."""
        readings_count = sensor_data.get("readings_count", 0)
        
        # Mocking multi-sensor behavior. In reality, this would come from the sensor array aggregation.
        # If readings_count > 0, we assume 3 active sensors.
        active_sensors = 3 if readings_count >= 10 else (2 if readings_count > 0 else 0)
        offline_sensors = max(0, 4 - active_sensors) # Assuming 4 sensors per barangay ideally
        degraded_sensors = 1 if (0 < readings_count < 10) else 0

        reliability_score = 0
        if active_sensors >= 3:
            reliability_score = 100
        elif active_sensors == 2:
            reliability_score = 75
        elif active_sensors == 1:
            reliability_score = 40

        return {
            "active_sensors": active_sensors,
            "offline_sensors": offline_sensors,
            "degraded_sensors": degraded_sensors,
            "reliability_score": reliability_score
        }

    @classmethod
    def _calculate_operational_urgency(
        cls, 
        fuzzy_result: Dict[str, Any], 
        ahp_result: Dict[str, Any],
        sensor_rel: Dict[str, Any],
        vulnerable_pop: int,
        total_pop: int
    ) -> Tuple[int, List[str]]:
        """
        Combines multiple factors to calculate a 0-100 operational urgency score.
        """
        score = 0.0
        factors = []
        
        # 1. Flood Risk Severity (0-40 points)
        risk = fuzzy_result.get("risk_level", RiskLevel.MEDIUM)
        risk_str = risk.value if isinstance(risk, RiskLevel) else str(risk)
        if risk_str == "CRITICAL":
            score += 40
            factors.append("Critical flood severity")
        elif risk_str == "HIGH":
            score += 30
            factors.append("High flood severity")
        elif risk_str == "MEDIUM":
            score += 15
        
        # 2. Rising trend penalty (+10 points)
        trend = fuzzy_result.get("trend", "stable")
        if trend == "rising":
            score += 10
            factors.append("Rising water levels detected")
            
        # 3. Rainfall intensity (+10 points max)
        rain_mm = float(fuzzy_result.get("rainfall_intensity_mm", 0.0))
        if rain_mm > 15.0:
            score += 10
            factors.append("Extreme rainfall intensity")
        elif rain_mm > 5.0:
            score += 5
            
        # 4. Humanitarian Impact (AHP Vulnerability) (0-30 points)
        ahp_score = float(ahp_result.get("priority_score", 0.0))
        impact_score = ahp_score * 30
        score += impact_score
        if ahp_score >= 0.65:
            factors.append("High vulnerable demographic concentration")
            
        # 5. Evacuation Pressure / Density (+10 points)
        if total_pop > 0 and (vulnerable_pop / total_pop) > 0.3:
            score += 10
            factors.append("High ratio of vulnerable to healthy residents")

        # Cap at 100
        final_score = min(100, int(score))
        return final_score, factors

    @classmethod
    def _determine_priority_level(
        cls, urgency_score: int, risk_level_str: str, ahp_result: Dict[str, Any]
    ) -> str:
        """Determines the final priority level category using multi-factor logic."""
        ahp_score = float(ahp_result.get("priority_score", 0.0))
        
        if risk_level_str == "CRITICAL" or (risk_level_str == "HIGH" and ahp_score >= 0.7) or urgency_score >= URGENCY_CRITICAL_MIN:
            return "CRITICAL"
        elif risk_level_str == "HIGH" or (risk_level_str == "MEDIUM" and ahp_score >= 0.8) or urgency_score >= URGENCY_HIGH_MIN:
            return "HIGH"
        elif risk_level_str == "MEDIUM" or urgency_score >= URGENCY_MEDIUM_MIN:
            return "MEDIUM"
        else:
            return "LOW"

    @classmethod
    def _estimate_evacuation_population(cls, total_residents: int, risk_level_str: str) -> int:
        if risk_level_str in ["HIGH", "CRITICAL"]:
            return int(total_residents * EVACUATION_FULL_RATIO)
        elif risk_level_str == "MEDIUM":
            return int(total_residents * EVACUATION_PARTIAL_RATIO)
        return 0

    @classmethod
    def _estimate_resources(
        cls,
        risk_level_str: str,
        affected_families: int,
        vulnerable_pop: int,
        evac_pop: int,
        fuzzy_result: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Applies deterministic operational formulas to estimate required resources.
        """
        items = []
        reasons = []

        if risk_level_str == "LOW":
            return items, ["Minimal operational response needed."]

        # Base supplies for MEDIUM and above
        food_qty = int(affected_families * FOOD_PACK_SCALING)
        if food_qty > 0:
            items.append({
                "item": "Food Packs",
                "quantity": food_qty,
                "reason": "Calculated based on affected household count"
            })
            reasons.append(f"Food allocated for {affected_families} affected families.")

        water_qty = int(affected_families * WATER_SCALING)
        if water_qty > 0:
            rain_mm = float(fuzzy_result.get("rainfall_intensity_mm", 0.0))
            rain_reason = " (Increased due to heavy rainfall)" if rain_mm > 10 else ""
            items.append({
                "item": "Water",
                "quantity": f"{water_qty}L",
                "reason": f"Baseline potable water allocation{rain_reason}"
            })

        # High and Critical supplies
        if risk_level_str in ["HIGH", "CRITICAL"]:
            hygiene_qty = int(vulnerable_pop * HYGIENE_SCALING)
            if hygiene_qty > 0:
                items.append({
                    "item": "Hygiene Kits",
                    "quantity": hygiene_qty,
                    "reason": "Required due to high vulnerable population in high-risk zones"
                })

            blanket_qty = int(evac_pop * BLANKET_SCALING)
            if blanket_qty > 0:
                items.append({
                    "item": "Blankets",
                    "quantity": blanket_qty,
                    "reason": "Scaled to match estimated evacuation center stress"
                })

        # Critical only supplies
        if risk_level_str == "CRITICAL" or vulnerable_pop > 50:
            med_qty = int(vulnerable_pop * MEDICINE_SCALING)
            if med_qty > 0:
                items.append({
                    "item": "Medicine Kits",
                    "quantity": med_qty,
                    "reason": "Deployed specifically to support elderly, infants, and pregnant residents"
                })
                reasons.append(f"Medicine kits scaled up due to {vulnerable_pop} vulnerable individuals.")

        return items, reasons

    @classmethod
    def _build_analysis_reasons(
        cls, 
        fuzzy_result: Dict[str, Any], 
        ahp_result: Dict[str, Any], 
        urgency_factors: List[str],
        sensor_rel: Dict[str, Any]
    ) -> List[str]:
        """Generates clear, operationally meaningful analysis reasons."""
        reasons = []
        
        # 1. Environmental
        risk_str = fuzzy_result.get("risk_level", RiskLevel.MEDIUM)
        if isinstance(risk_str, RiskLevel): risk_str = risk_str.value
        reasons.append(f"Flood hazard classified as {risk_str}.")
        
        trend = fuzzy_result.get("trend", "stable")
        if trend != "stable":
            reasons.append(f"Water level trend is continuously {trend}.")
            
        rain = float(fuzzy_result.get("rainfall_intensity_mm", 0.0))
        if rain > 5.0:
            reasons.append(f"Significant rainfall intensity detected ({rain}mm).")
            
        # 2. Humanitarian
        ahp_score = float(ahp_result.get("priority_score", 0.0))
        if ahp_score >= 0.65:
            reasons.append("High vulnerability score detected due to local demographics.")
            
        # 3. Urgency Factors
        for factor in urgency_factors:
            if factor not in " ".join(reasons):
                reasons.append(f"Operational Urgency Driver: {factor}.")
                
        # 4. Sensor status
        active = sensor_rel.get("active_sensors", 0)
        offline = sensor_rel.get("offline_sensors", 0)
        if offline > 0:
            reasons.append(f"Warning: {offline} sensors offline, analysis confidence reduced.")
        elif active >= 3:
            reasons.append(f"{active} active sensors confirmed escalation.")

        return reasons
