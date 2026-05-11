"""
Pydantic models and schemas for the AI decision service.
Handles request/response validation and serialization.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Enumeration for flood risk levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendedAction(str, Enum):
    """Enumeration for relief and response actions (rule-based suggestions)."""
    SAFE = "SAFE"
    MONITOR = "MONITOR"
    PREPARE = "PREPARE"
    PREPARE_ADDITIONAL_RESOURCES = "PREPARE ADDITIONAL RESOURCES"
    PREPARE_FOOD_PACKS = "PREPARE FOOD PACKS"
    PARTIAL_EVACUATION = "PARTIAL EVACUATION"
    IMMEDIATE_RELIEF = "IMMEDIATE RELIEF"
    DEPLOY_RESCUE_TEAM = "DEPLOY RESCUE TEAM"
    SEND_MEDICAL_ASSISTANCE = "SEND MEDICAL ASSISTANCE"


# ============ Request Models ============


class DecisionRequest(BaseModel):
    """
    Request model for the decision endpoint.
    
    Fields:
        barangay_id: Identifier for the barangay (community area)
        override_action: Optional human-selected action (human-in-the-loop)
    """
    barangay_id: int = Field(..., description="Unique identifier for the barangay")
    override_action: Optional[RecommendedAction] = Field(
        default=None,
        description="If set, this action becomes the official recommendation while AI suggestions remain advisory",
    )


# ============ Internal Models ============


class SensorReading(BaseModel):
    """
    Model for sensor data aggregated from MongoDB.
    
    Fields:
        avg_water_level: Average water level in the last 5-10 minutes (in cm)
        max_water_level: Maximum water level in the last 5-10 minutes (in cm)
        trend: Direction of water level change (rising, falling, stable)
        timestamp: When the reading was taken
    """
    avg_water_level: float = Field(..., description="Average water level in cm")
    max_water_level: float = Field(..., description="Maximum water level in cm")
    trend: str = Field(..., description="Water level trend: rising, falling, or stable")
    timestamp: str = Field(..., description="Timestamp of the reading")


class HouseholdVulnerability(BaseModel):
    """
    Model for household vulnerability metrics aggregated from Supabase.
    
    Fields:
        household_id: Identifier for the household
        elderly_count: Number of residents aged 60 or above
        infant_count: Number of residents aged 2 or below
        pregnant_count: Number of pregnant residents
        pwd_count: Number of residents with disabilities (PWD)
    """
    household_id: str = Field(..., description="Unique household identifier")
    elderly_count: int = Field(default=0, description="Number of elderly residents (age >= 60)")
    infant_count: int = Field(default=0, description="Number of infants (age <= 2)")
    pregnant_count: int = Field(default=0, description="Number of pregnant residents")
    pwd_count: int = Field(default=0, description="Number of PWD residents")


class FuzzyLogicOutput(BaseModel):
    """
    Output from the Fuzzy Logic service.
    
    Fields:
        risk_level: Overall flood risk assessment
        confidence_score: Confidence in the risk assessment (0-1)
        explanation: Human-readable explanation of the assessment
    """
    risk_level: RiskLevel = Field(..., description="Flood risk level: LOW, MEDIUM, or HIGH")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    explanation: str = Field(..., description="Explanation of the risk assessment")


class AHPOutput(BaseModel):
    """
    Output from the AHP (Analytic Hierarchy Process) service.
    
    Fields:
        priority_score: Overall priority score for relief allocation (0-1)
        explanation: Human-readable explanation of priority calculation
    """
    priority_score: float = Field(..., ge=0.0, le=1.0, description="Priority score (0-1)")
    explanation: str = Field(..., description="Explanation of priority calculation")


# ============ Response Models ============


class Suggestion(BaseModel):
    """
    A single ranked, explainable recommendation from the rule-based engine.
    """
    priority_rank: int = Field(..., ge=1, description="1 = most urgent after ranking")
    action: RecommendedAction = Field(..., description="Suggested action")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in this suggestion (0-1)")
    reason: str = Field(..., description="Rule-based rationale tied to risk, trend, and vulnerability")


class DecisionResponse(BaseModel):
    """
    Response model for the decision endpoint.
    Contains the AI recommendation and supporting information.
    
    Fields:
        barangay_id: The barangay for which this decision was made
        risk_level: Flood risk assessment
        priority_score: Vulnerability priority score
        recommended_action: Recommended action based on risk and priority
        confidence_score: Overall confidence in the recommendation
        explanation: Human-readable explanation of the decision
        override_action: Optional human override of the recommendation
        fuzzy_explanation: Detailed explanation from fuzzy logic
        ahp_explanation: Detailed explanation from AHP calculation
        suggestions: Ranked list of at least three explainable AI suggestions
    """
    barangay_id: int = Field(..., description="Barangay identifier")
    risk_level: RiskLevel = Field(..., description="Flood risk level")
    priority_score: float = Field(..., ge=0.0, le=1.0, description="Household priority score")
    suggestions: List[Suggestion] = Field(
        ...,
        min_length=3,
        description="At least three ranked suggestions (urgency, then confidence)",
    )
    recommended_action: RecommendedAction = Field(..., description="Recommended action")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall confidence score")
    explanation: str = Field(..., description="Summary explanation of the decision")
    override_action: Optional[RecommendedAction] = Field(
        default=None,
        description="Optional human override of the recommendation"
    )
    fuzzy_explanation: str = Field(..., description="Detailed fuzzy logic explanation")
    ahp_explanation: str = Field(..., description="Detailed AHP explanation")


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Status message")
