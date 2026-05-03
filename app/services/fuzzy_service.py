"""
Fuzzy Logic service for flood risk assessment.
Uses rule-based fuzzy logic to classify water levels into risk categories.
"""

from enum import Enum
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class FuzzyRiskLevel(Enum):
    """Fuzzy logic risk levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FuzzyLogicService:
    """
    Implements fuzzy logic for flood risk assessment.
    
    Fuzzy sets are defined based on water level thresholds:
    - LOW: avg < 50cm OR trend = falling
    - MEDIUM: 50cm <= avg <= 100cm OR trend = stable
    - HIGH: avg > 100cm OR trend = rising
    
    Rules are based on domain knowledge and can be adjusted
    for different regions or flood scenarios.
    """
    
    # Thresholds (in cm) - these can be configured per region
    LOW_THRESHOLD = 50.0
    MEDIUM_THRESHOLD = 100.0
    CRITICAL_THRESHOLD = 150.0
    
    @classmethod
    def assess_risk(cls, avg_water_level: float, max_water_level: float, trend: str) -> Dict[str, Any]:
        """
        Assess flood risk using fuzzy logic rules.
        
        Args:
            avg_water_level: Average water level in cm
            max_water_level: Maximum water level in cm
            trend: Water level trend (rising, falling, stable)
        
        Returns:
            Dictionary with:
                - risk_level: LOW, MEDIUM, or HIGH
                - confidence_score: Confidence in assessment (0-1)
                - explanation: Human-readable explanation
                - membership_scores: Fuzzy membership scores for each level
        """
        
        # Validate inputs
        if avg_water_level < 0 or max_water_level < 0:
            logger.warning(f"Invalid water levels: avg={avg_water_level}, max={max_water_level}")
            avg_water_level = max(0, avg_water_level)
            max_water_level = max(0, max_water_level)
        
        if trend.lower() not in ["rising", "falling", "stable"]:
            logger.warning(f"Invalid trend: {trend}, defaulting to stable")
            trend = "stable"
        
        # Calculate membership scores for each risk level
        membership_scores = cls._calculate_membership_scores(
            avg_water_level, max_water_level, trend
        )
        
        # Determine primary risk level (highest membership)
        risk_level = max(membership_scores, key=membership_scores.get)
        confidence = membership_scores[risk_level]
        
        # Generate explanation
        explanation = cls._generate_explanation(
            avg_water_level, max_water_level, trend, risk_level, confidence
        )
        
        logger.info(f"Risk assessment: level={risk_level}, confidence={confidence:.2f}, trend={trend}")
        
        return {
            "risk_level": risk_level,
            "confidence_score": confidence,
            "explanation": explanation,
            "membership_scores": membership_scores,
            "avg_water_level": avg_water_level,
            "max_water_level": max_water_level,
            "trend": trend
        }
    
    @classmethod
    def _calculate_membership_scores(
        cls, avg_water_level: float, max_water_level: float, trend: str
    ) -> Dict[str, float]:
        """
        Calculate fuzzy membership scores for each risk level.
        Uses triangular and trapezoidal membership functions.
        
        Args:
            avg_water_level: Average water level
            max_water_level: Maximum water level
            trend: Water level trend
        
        Returns:
            Dictionary with membership scores for each risk level
        """
        
        # Rule 1: Based on average water level
        if avg_water_level < cls.LOW_THRESHOLD:
            level_score = 0.8 - (avg_water_level / cls.LOW_THRESHOLD * 0.3)
        elif avg_water_level < cls.MEDIUM_THRESHOLD:
            # Linear interpolation between LOW and MEDIUM
            progress = (avg_water_level - cls.LOW_THRESHOLD) / (
                cls.MEDIUM_THRESHOLD - cls.LOW_THRESHOLD
            )
            level_score = 0.5 + (progress * 0.3)
        elif avg_water_level < cls.CRITICAL_THRESHOLD:
            # Linear interpolation between MEDIUM and HIGH
            progress = (avg_water_level - cls.MEDIUM_THRESHOLD) / (
                cls.CRITICAL_THRESHOLD - cls.MEDIUM_THRESHOLD
            )
            level_score = 0.8 + (progress * 0.2)
        else:
            level_score = 1.0
        
        # Rule 2: Based on trend (amplifies or dampens the score)
        trend_lower = trend.lower()
        if trend_lower == "rising":
            level_score = min(1.0, level_score + 0.15)  # Rising increases risk
        elif trend_lower == "falling":
            level_score = max(0.0, level_score - 0.15)  # Falling decreases risk
        # stable: no change
        
        # Rule 3: Based on maximum water level spike
        if max_water_level > cls.CRITICAL_THRESHOLD:
            level_score = min(1.0, level_score + 0.1)  # Recent spike increases risk
        
        # Classify into discrete levels based on membership score
        # Use hysteresis to avoid oscillation between levels
        if level_score < 0.35:
            return {"LOW": 0.9, "MEDIUM": 0.1, "HIGH": 0.0}
        elif level_score < 0.65:
            return {"LOW": 0.2, "MEDIUM": 0.8, "HIGH": 0.1}
        else:
            return {"LOW": 0.0, "MEDIUM": 0.2, "HIGH": 0.9}
    
    @classmethod
    def _generate_explanation(
        cls, avg_water_level: float, max_water_level: float, trend: str,
        risk_level: str, confidence: float
    ) -> str:
        """
        Generate a human-readable explanation of the risk assessment.
        
        Args:
            avg_water_level: Average water level
            max_water_level: Maximum water level
            trend: Water level trend
            risk_level: Assessed risk level
            confidence: Confidence score
        
        Returns:
            Human-readable explanation
        """
        
        parts = []
        
        # Water level summary
        if avg_water_level < cls.LOW_THRESHOLD:
            parts.append(f"Average water level is {avg_water_level:.1f}cm, well below warning threshold.")
        elif avg_water_level < cls.MEDIUM_THRESHOLD:
            parts.append(
                f"Average water level is {avg_water_level:.1f}cm, approaching caution threshold "
                f"({cls.LOW_THRESHOLD}cm)."
            )
        elif avg_water_level < cls.CRITICAL_THRESHOLD:
            parts.append(
                f"Average water level is {avg_water_level:.1f}cm, in danger zone "
                f"({cls.MEDIUM_THRESHOLD}-{cls.CRITICAL_THRESHOLD}cm)."
            )
        else:
            parts.append(
                f"Average water level is {avg_water_level:.1f}cm, critically high "
                f"(above {cls.CRITICAL_THRESHOLD}cm)."
            )
        
        # Trend summary
        trend_lower = trend.lower()
        if trend_lower == "rising":
            parts.append("Water levels are RISING, situation deteriorating.")
        elif trend_lower == "falling":
            parts.append("Water levels are FALLING, situation improving.")
        else:
            parts.append("Water levels are STABLE.")
        
        # Peak summary
        if max_water_level > cls.CRITICAL_THRESHOLD:
            parts.append(f"Recent peak of {max_water_level:.1f}cm indicates potential flooding risk.")
        
        # Risk assessment
        confidence_pct = int(confidence * 100)
        parts.append(
            f"Risk assessment: {risk_level} (confidence: {confidence_pct}%)"
        )
        
        return " ".join(parts)
