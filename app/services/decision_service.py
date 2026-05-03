"""
Decision service that combines Fuzzy Logic and AHP into a final recommendation.
Implements human-in-the-loop override support.
"""

from typing import Dict, Any, Optional
from app.services.fuzzy_service import FuzzyLogicService
from app.services.ahp_service import AHPService
from app.models.schemas import RecommendedAction, RiskLevel
from app.database.mongodb import MongoDBConnection
from app.database.supabase import SupabaseConnection
import logging

logger = logging.getLogger(__name__)


class DecisionService:
    """
    Combines fuzzy logic risk assessment with AHP vulnerability scoring
    to produce a final relief allocation recommendation.
    
    Decision matrix:
    - Risk: HIGH + Priority: HIGH/CRITICAL -> IMMEDIATE RELIEF
    - Risk: HIGH + Priority: LOW/MODERATE -> PREPARE
    - Risk: MEDIUM + Priority: HIGH/CRITICAL -> IMMEDIATE RELIEF
    - Risk: MEDIUM + Priority: MODERATE -> PREPARE
    - Risk: LOW + Priority: Any -> SAFE or PREPARE
    """
    
    # Decision thresholds
    HIGH_PRIORITY_THRESHOLD = 0.65
    MEDIUM_PRIORITY_THRESHOLD = 0.35
    MEDIUM_RISK_THRESHOLD = 0.65  # Based on fuzzy confidence
    
    @classmethod
    def make_decision(cls, barangay_id: int, override_action: Optional[RecommendedAction] = None) -> Dict[str, Any]:
        """
        Make a relief allocation decision for a barangay.
        
        Args:
            barangay_id: Identifier for the barangay
            override_action: Optional human override (SAFE, PREPARE, IMMEDIATE_RELIEF)
        
        Returns:
            Dictionary with final decision and supporting information
        """
        
        logger.info(f"Making decision for barangay {barangay_id}")
        
        try:
            # Step 1: Fetch sensor data and assess risk
            sensor_data = MongoDBConnection.get_sensor_data(barangay_id, minutes=10)
            
            fuzzy_result = FuzzyLogicService.assess_risk(
                avg_water_level=sensor_data["avg_water_level"],
                max_water_level=sensor_data["max_water_level"],
                trend=sensor_data["trend"]
            )
            
            # Step 2: Fetch household data and assess vulnerability
            household_data = SupabaseConnection.get_household_vulnerability(barangay_id)
            
            ahp_result = AHPService.calculate_priority(
                elderly_count=household_data["elderly_count"],
                infant_count=household_data["infant_count"],
                pregnant_count=household_data["pregnant_count"],
                pwd_count=household_data["pwd_count"],
                total_residents=household_data.get("total_residents", 5)
            )
            
            # Step 3: Combine results into recommendation
            recommendation = cls._combine_assessments(
                fuzzy_result=fuzzy_result,
                ahp_result=ahp_result,
                override_action=override_action
            )
            
            logger.info(
                f"Decision made for barangay {barangay_id}: "
                f"{recommendation['recommended_action']} (confidence: {recommendation['confidence_score']:.2f})"
            )
            
            return {
                "barangay_id": barangay_id,
                "risk_level": fuzzy_result["risk_level"],
                "priority_score": ahp_result["priority_score"],
                "recommended_action": recommendation["recommended_action"],
                "confidence_score": recommendation["confidence_score"],
                "explanation": recommendation["summary_explanation"],
                "override_action": override_action,
                "fuzzy_explanation": fuzzy_result["explanation"],
                "ahp_explanation": ahp_result["explanation"],
                # Additional metadata
                "_metadata": {
                    "sensor_readings_count": sensor_data.get("readings_count", 0),
                    "total_residents": household_data.get("total_residents", 0),
                    "vulnerability_factors": ahp_result.get("vulnerability_factors", [])
                }
            }
            
        except Exception as e:
            logger.error(f"Error making decision for barangay {barangay_id}: {str(e)}")
            # Return a safe default in case of error
            return {
                "barangay_id": barangay_id,
                "risk_level": RiskLevel.MEDIUM,
                "priority_score": 0.5,
                "recommended_action": RecommendedAction.PREPARE,
                "confidence_score": 0.3,
                "explanation": f"Decision system error: {str(e)}. Recommend PREPARE as precaution.",
                "override_action": override_action,
                "fuzzy_explanation": "Error retrieving sensor data",
                "ahp_explanation": "Error retrieving household data",
                "_metadata": {
                    "error": str(e)
                }
            }
    
    @classmethod
    def _combine_assessments(cls, fuzzy_result: Dict[str, Any],
                            ahp_result: Dict[str, Any],
                            override_action: Optional[RecommendedAction] = None) -> Dict[str, Any]:
        """
        Combine fuzzy logic risk assessment with AHP priority scoring
        into a final recommendation.
        
        Args:
            fuzzy_result: Output from FuzzyLogicService
            ahp_result: Output from AHPService
            override_action: Optional human override
        
        Returns:
            Dictionary with recommended_action and confidence_score
        """
        
        risk_level = fuzzy_result["risk_level"]
        risk_confidence = fuzzy_result["confidence_score"]
        priority_score = ahp_result["priority_score"]
        
        # If human override is provided, use it
        if override_action:
            logger.warning(
                f"Using human override: {override_action} "
                f"(original recommendation would be based on risk={risk_level}, priority={priority_score:.2f})"
            )
            return {
                "recommended_action": override_action,
                "confidence_score": 0.95,  # High confidence in human override
                "summary_explanation": f"Human override applied: {override_action}"
            }
        
        # Decision logic based on risk level and priority
        if risk_level == "HIGH":
            if priority_score >= cls.HIGH_PRIORITY_THRESHOLD:
                # High risk + high vulnerability = immediate relief
                action = RecommendedAction.IMMEDIATE_RELIEF
                confidence = min(0.95, risk_confidence + 0.1)
            elif priority_score >= cls.MEDIUM_PRIORITY_THRESHOLD:
                # High risk + moderate vulnerability = prepare/relief
                action = RecommendedAction.PREPARE
                confidence = risk_confidence * 0.9
            else:
                # High risk but low vulnerability = prepare
                action = RecommendedAction.PREPARE
                confidence = risk_confidence * 0.8
        
        elif risk_level == "MEDIUM":
            if priority_score >= cls.HIGH_PRIORITY_THRESHOLD:
                # Medium risk + high vulnerability = prepare/relief
                action = RecommendedAction.IMMEDIATE_RELIEF
                confidence = risk_confidence * 0.85
            elif priority_score >= cls.MEDIUM_PRIORITY_THRESHOLD:
                # Medium risk + moderate vulnerability = prepare
                action = RecommendedAction.PREPARE
                confidence = (risk_confidence + priority_score) / 2 * 0.85
            else:
                # Medium risk + low vulnerability = safe/prepare
                action = RecommendedAction.PREPARE
                confidence = risk_confidence * 0.7
        
        else:  # LOW risk
            if priority_score >= cls.HIGH_PRIORITY_THRESHOLD:
                # Low risk but high vulnerability = prepare anyway
                action = RecommendedAction.PREPARE
                confidence = risk_confidence * 0.8
            else:
                # Low risk + low vulnerability = safe
                action = RecommendedAction.SAFE
                confidence = risk_confidence * 0.85
        
        # Generate combined explanation
        summary = cls._generate_combined_explanation(
            risk_level, priority_score, action, confidence
        )
        
        return {
            "recommended_action": action,
            "confidence_score": max(0.0, min(1.0, confidence)),
            "summary_explanation": summary
        }
    
    @classmethod
    def _generate_combined_explanation(cls, risk_level: str, priority_score: float,
                                      action: RecommendedAction, confidence: float) -> str:
        """
        Generate a combined explanation of the decision.
        
        Args:
            risk_level: Flood risk level (LOW, MEDIUM, HIGH)
            priority_score: Household priority score (0-1)
            action: Recommended action
            confidence: Confidence score (0-1)
        
        Returns:
            Human-readable explanation
        """
        
        confidence_pct = int(confidence * 100)
        priority_pct = int(priority_score * 100)
        
        # Determine priority level
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
                f"indicates immediate relief is needed (confidence: {confidence_pct}%)."
            )
        elif action == RecommendedAction.PREPARE:
            parts.append(
                f"warrants preparation for potential evacuation (confidence: {confidence_pct}%)."
            )
        else:  # SAFE
            parts.append(
                f"suggests the area is currently safe with no urgent action needed (confidence: {confidence_pct}%)."
            )
        
        parts.append(f"Recommendation: {action.value}")
        
        return " ".join(parts)
