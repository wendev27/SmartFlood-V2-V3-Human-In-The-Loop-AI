"""
Pydantic models and schemas for the AI decision service.
Handles request/response validation and serialization.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Enumeration for flood risk levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


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
    FULL_EVACUATION = "FULL EVACUATION"


class RecommendationStatus(str, Enum):
    """Enumeration for the status of the recommendation."""
    STABLE = "stable"
    MONITORING = "monitoring"
    CRITICAL = "critical"
    RESOURCE_SHORTAGE = "resource_shortage"


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


class FuzzyAssessmentDetail(BaseModel):
    """Structured fuzzy output for API explainability."""
    hazard_descriptor: str = Field(..., description="Official-style hazard label")
    risk_level: RiskLevel = Field(..., description="Winning LOW/MEDIUM/HIGH class")
    depth_avg_m: float = Field(..., description="Average depth in meters")
    depth_max_m: float = Field(..., description="Peak depth in meters")
    trend: str = Field(..., description="rising | falling | stable")
    rainfall_intensity_mm: float = Field(..., ge=0.0, description="Rainfall intensity input (mm)")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    membership_scores: Dict[str, float] = Field(default_factory=dict)
    reasoning_steps: List[str] = Field(default_factory=list)


class AHPPriorityBreakdown(BaseModel):
    """Transparent AHP-style breakdown returned to clients."""
    priority_score: float = Field(..., ge=0.0, le=1.0)
    weights_percent: Dict[str, float] = Field(default_factory=dict)
    weighted_contributions: Dict[str, float] = Field(default_factory=dict)
    sub_scores: Dict[str, float] = Field(default_factory=dict)
    breakdown_lines: List[str] = Field(default_factory=list)
    vulnerability_factors: List[str] = Field(default_factory=list)
    factor_rationale: Dict[str, str] = Field(default_factory=dict)


class ExplainabilityPayload(BaseModel):
    """Cross-module explanations for human-in-the-loop review."""
    why_flood_risk_classified: str = Field(..., description="Why fuzzy logic chose the hazard class")
    why_barangay_priority: str = Field(..., description="Why the barangay vulnerability index is what it is")
    top_recommendations_explained: List[str] = Field(
        default_factory=list,
        description="Per-suggestion drivers: hazard, trend, rainfall, vulnerability",
    )


class RecommendedItem(BaseModel):
    """Specific relief item recommendation."""
    item: str = Field(..., description="Name of the recommended item")
    quantity: str = Field(..., description="Quantity of the item (can be int or string with units)")
    reason: str = Field(..., description="Operational reason for recommending this item")


class InventoryConstraint(BaseModel):
    """Details about an inventory shortage constraint."""
    item: str = Field(..., description="Name of the constrained item")
    requested: int = Field(..., description="Originally requested amount")
    allocated: int = Field(..., description="Actual allocated amount due to shortage")
    shortage_reason: str = Field(..., description="Explanation of the shortage")


class SensorReliability(BaseModel):
    """Metadata regarding the reliability of the sensor array."""
    active_sensors: int = Field(default=0, description="Number of active sensors")
    offline_sensors: int = Field(default=0, description="Number of offline sensors")
    degraded_sensors: int = Field(default=0, description="Number of degraded sensors")
    reliability_score: int = Field(default=0, description="0-100 reliability score")


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
    fuzzy_assessment: Optional[FuzzyAssessmentDetail] = Field(
        default=None,
        description="Structured fuzzy outputs (memberships, reasoning steps, hazard label)",
    )
    ahp_breakdown: Optional[AHPPriorityBreakdown] = Field(
        default=None,
        description="Weights, sub-scores, and line-by-line AHP contribution audit",
    )
    explainability: Optional[ExplainabilityPayload] = Field(
        default=None,
        description="Narrative links between hazard, priority, and ranked recommendations",
    )
    
    # New Operational Fields
    priority_level: str = Field(..., description="Multi-factor operational priority level")
    analysis_confidence: int = Field(..., description="0-100 scaled analysis confidence")
    affected_families: int = Field(..., description="Estimated affected families")
    affected_population: int = Field(..., description="Total affected population")
    estimated_evacuation_population: int = Field(..., description="Estimated population needing evacuation")
    recommended_items: List[RecommendedItem] = Field(default_factory=list, description="Specific relief item recommendations")
    analysis_reason: List[str] = Field(default_factory=list, description="List of specific operational reasons")
    operational_urgency_score: int = Field(..., description="0-100 operational urgency score")
    recommendation_status: RecommendationStatus = Field(..., description="Status of the recommendation")
    inventory_constraints: List[InventoryConstraint] = Field(default_factory=list, description="Any inventory shortage constraints applied")
    adjusted_recommendations: bool = Field(default=False, description="True if recommendations were reduced due to inventory shortages")
    recommendation_source: List[str] = Field(default_factory=list, description="Sources involved in the recommendation generation")
    operational_notes: List[str] = Field(default_factory=list, description="Additional operational observations")
    sensor_reliability: Optional[SensorReliability] = Field(default=None, description="Metadata regarding sensor array health")


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Status message")


class CityWideDetailedReasoning(BaseModel):
    """Detailed reasoning components for a city-wide analysis item."""
    flood_analysis: str
    vulnerability_analysis: str
    contributing_factors: List[str]
    recommendation_reasoning: List[str]
    ahp_breakdown: Optional[AHPPriorityBreakdown] = None
    fuzzy_assessment: Optional[FuzzyAssessmentDetail] = None


class CityWideAnalysisItem(BaseModel):
    """
    A single barangay's analysis result for the city-wide dashboard.
    """
    barangay_id: int
    barangay_name: str
    risk_level: RiskLevel
    confidence_score: float
    recommended_items: List[str]
    short_reason: str
    detailed_reasoning: CityWideDetailedReasoning


class CityWideAnalysisResponse(BaseModel):
    """
    City-wide analysis response containing all barangays.
    """
    city_analysis: List[CityWideAnalysisItem]
