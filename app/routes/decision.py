"""
API routes for the decision service.
Handles HTTP requests and responses.
"""

from fastapi import APIRouter, HTTPException, status
from app.models.schemas import (
    AHPPriorityBreakdown,
    DecisionRequest,
    DecisionResponse,
    ExplainabilityPayload,
    FuzzyAssessmentDetail,
    HealthCheckResponse,
    Suggestion,
    CityWideAnalysisResponse,
)
from app.services.decision_service import DecisionService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check",
    description="Check if the service is running and responding"
)
async def health_check() -> HealthCheckResponse:
    """
    Health check endpoint.
    
    Returns:
        HealthCheckResponse with status and message
    """
    return HealthCheckResponse(
        status="healthy",
        message="AI Decision Service is running"
    )


@router.post(
    "/decision",
    response_model=DecisionResponse,
    summary="Get Relief Allocation Decision",
    description="Get AI recommendation for relief allocation based on flood risk and household vulnerability",
    status_code=status.HTTP_200_OK
)
async def get_decision(request: DecisionRequest) -> DecisionResponse:
    """
    Get an AI recommendation for relief allocation.
    
    This endpoint combines:
    1. Fuzzy Logic analysis of flood risk from sensor data
    2. AHP analysis of household vulnerability
    3. Decision logic to recommend action
    
    Args:
        request: DecisionRequest with barangay_id
    
    Returns:
        DecisionResponse with recommendation and explanation
    
    Raises:
        HTTPException: If barangay_id is invalid or service unavailable
    """
    
    try:
        # Validate barangay_id
        if request.barangay_id <= 0:
            logger.warning(f"Invalid barangay_id: {request.barangay_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="barangay_id must be a positive integer"
            )
        
        logger.info(f"Processing decision request for barangay {request.barangay_id}")
        
        # Get the decision from the service
        decision = DecisionService.make_decision(
            barangay_id=request.barangay_id,
            override_action=request.override_action,
        )

        suggestions = [Suggestion(**s) for s in decision["suggestions"]]

        fa = decision.get("fuzzy_assessment")
        ab = decision.get("ahp_breakdown")
        ex = decision.get("explainability")

        response = DecisionResponse(
            barangay_id=decision["barangay_id"],
            risk_level=decision["risk_level"],
            priority_score=decision["priority_score"],
            suggestions=suggestions,
            recommended_action=decision["recommended_action"],
            confidence_score=decision["confidence_score"],
            explanation=decision["explanation"],
            override_action=decision["override_action"],
            fuzzy_explanation=decision["fuzzy_explanation"],
            ahp_explanation=decision["ahp_explanation"],
            fuzzy_assessment=FuzzyAssessmentDetail(**fa) if fa else None,
            ahp_breakdown=AHPPriorityBreakdown(**ab) if ab else None,
            explainability=ExplainabilityPayload(**ex) if ex else None,
        )
        
        logger.info(
            f"Decision request completed: barangay={request.barangay_id}, "
            f"action={response.recommended_action}"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing decision request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Service temporarily unavailable."
        )


@router.post(
    "/decision/city-wide",
    response_model=CityWideAnalysisResponse,
    summary="Get City-Wide Decision Analysis",
    description="Automatically evaluates ALL barangays using fuzzy+AHP decision pipeline and returns ranked priorities.",
    status_code=status.HTTP_200_OK
)
async def get_city_wide_decision() -> CityWideAnalysisResponse:
    """
    Get city-wide disaster prioritization.
    """
    logger.info("Processing city-wide decision request")
    
    try:
        analysis_results = DecisionService.make_city_wide_decision()
        response = CityWideAnalysisResponse(city_analysis=analysis_results)
        logger.info(f"City-wide decision request completed: {len(analysis_results)} barangays analyzed")
        return response
    except Exception as e:
        logger.error(f"Unexpected error processing city-wide decision request: {str(e)}", exc_info=True)
        # Even on top-level error, we return empty array instead of crashing as requested
        return CityWideAnalysisResponse(city_analysis=[])
