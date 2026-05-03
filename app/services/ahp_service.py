"""
AHP (Analytic Hierarchy Process) service for household vulnerability assessment.
Evaluates vulnerability based on demographics and special needs.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class AHPService:
    """
    Implements AHP for household vulnerability scoring.
    
    AHP combines multiple vulnerability factors with weighted scores:
    - Elderly residents (60+): High vulnerability
    - Infants (0-2): Very high vulnerability
    - Pregnant residents: Medium vulnerability
    - PWD residents: High vulnerability
    
    Weights reflect evacuation difficulty and medical needs.
    Final score is normalized to 0-1 range.
    """
    
    # AHP weights for each vulnerability factor
    # These are normalized so they sum to 1.0
    WEIGHTS = {
        "elderly": 0.35,      # High priority - mobility issues, medical needs
        "infant": 0.40,       # Highest priority - complete dependence
        "pregnant": 0.15,     # Medium priority - medical monitoring needed
        "pwd": 0.10           # Priority based on severity (here general weight)
    }
    
    # Normalize factor: How much each person in a category contributes to priority
    # Adjusted based on typical household sizes (~5 people)
    NORMALIZATION_BASE = 5
    
    @classmethod
    def calculate_priority(cls, elderly_count: int, infant_count: int,
                          pregnant_count: int, pwd_count: int,
                          total_residents: int = 0) -> Dict[str, Any]:
        """
        Calculate household vulnerability priority score using AHP.
        
        Args:
            elderly_count: Number of elderly residents (age >= 60)
            infant_count: Number of infants (age <= 2)
            pregnant_count: Number of pregnant residents
            pwd_count: Number of PWD residents
            total_residents: Total number of residents (for normalization)
        
        Returns:
            Dictionary with:
                - priority_score: Final normalized score (0-1)
                - sub_scores: Individual scores for each factor
                - explanation: Human-readable explanation
                - vulnerability_factors: List of active vulnerability factors
        """
        
        # Ensure non-negative counts
        elderly_count = max(0, elderly_count)
        infant_count = max(0, infant_count)
        pregnant_count = max(0, pregnant_count)
        pwd_count = max(0, pwd_count)
        
        if total_residents == 0:
            total_residents = elderly_count + infant_count + pregnant_count + pwd_count + 1
        
        # Calculate raw scores for each vulnerability factor
        elderly_score = cls._calculate_factor_score(elderly_count, total_residents, "elderly")
        infant_score = cls._calculate_factor_score(infant_count, total_residents, "infant")
        pregnant_score = cls._calculate_factor_score(pregnant_count, total_residents, "pregnant")
        pwd_score = cls._calculate_factor_score(pwd_count, total_residents, "pwd")
        
        # Combine using AHP weights (weighted sum)
        combined_score = (
            elderly_score * cls.WEIGHTS["elderly"] +
            infant_score * cls.WEIGHTS["infant"] +
            pregnant_score * cls.WEIGHTS["pregnant"] +
            pwd_score * cls.WEIGHTS["pwd"]
        )
        
        # Normalize to 0-1 range and apply non-linear scaling
        # This ensures that households with vulnerable members get higher priority
        priority_score = cls._normalize_score(combined_score)
        
        # Identify which vulnerability factors are present
        vulnerability_factors = []
        if elderly_count > 0:
            vulnerability_factors.append(f"Elderly ({elderly_count})")
        if infant_count > 0:
            vulnerability_factors.append(f"Infants ({infant_count})")
        if pregnant_count > 0:
            vulnerability_factors.append(f"Pregnant ({pregnant_count})")
        if pwd_count > 0:
            vulnerability_factors.append(f"PWD ({pwd_count})")
        
        # Generate explanation
        explanation = cls._generate_explanation(
            elderly_count, infant_count, pregnant_count, pwd_count,
            priority_score, vulnerability_factors
        )
        
        logger.info(
            f"AHP Priority Score: {priority_score:.3f} - "
            f"Factors: {', '.join(vulnerability_factors) if vulnerability_factors else 'None'}"
        )
        
        return {
            "priority_score": priority_score,
            "sub_scores": {
                "elderly_score": elderly_score,
                "infant_score": infant_score,
                "pregnant_score": pregnant_score,
                "pwd_score": pwd_score
            },
            "explanation": explanation,
            "vulnerability_factors": vulnerability_factors,
            "household_composition": {
                "elderly": elderly_count,
                "infant": infant_count,
                "pregnant": pregnant_count,
                "pwd": pwd_count,
                "total_residents": total_residents
            }
        }
    
    @classmethod
    def _calculate_factor_score(cls, count: int, total_residents: int, factor_type: str) -> float:
        """
        Calculate score for a specific vulnerability factor.
        Score increases with count, normalized by household size.
        
        Args:
            count: Number of people in this vulnerability category
            total_residents: Total residents in household
            factor_type: Type of vulnerability (elderly, infant, pregnant, pwd)
        
        Returns:
            Score for this factor (0-1, unbounded in calculation)
        """
        
        if total_residents == 0:
            return 0.0
        
        # Proportion of household in this category
        proportion = count / total_residents
        
        # Apply factor-specific scoring
        # Infants and elderly get higher scores for same proportion
        if factor_type == "infant":
            # Infants are very vulnerable - high impact even in small numbers
            factor_score = min(1.0, proportion * 3.0)
        elif factor_type == "elderly":
            # Elderly are highly vulnerable
            factor_score = min(1.0, proportion * 2.5)
        elif factor_type == "pregnant":
            # Pregnant people need care but less critical than infants/elderly
            factor_score = min(1.0, proportion * 1.5)
        elif factor_type == "pwd":
            # PWD impact depends on severity (general weight here)
            factor_score = min(1.0, proportion * 1.2)
        else:
            factor_score = proportion
        
        return factor_score
    
    @classmethod
    def _normalize_score(cls, combined_score: float) -> float:
        """
        Normalize combined score to 0-1 range using sigmoid-like function.
        This ensures scores are proportional but not unbounded.
        
        Args:
            combined_score: Raw combined score from weighted factors
        
        Returns:
            Normalized priority score (0-1)
        """
        
        # Sigmoid-like normalization: helps compress extreme values
        # while preserving relative ordering
        # Formula: 1 / (1 + e^(-x*2))
        # This maps [-inf, inf] -> [0, 1] with steepness at 0
        
        # For practical purposes, cap the input to avoid numerical issues
        x = min(3.0, max(-3.0, combined_score * 2.0))
        
        # Approximate sigmoid using simpler formula
        # For reasonable inputs, this gives values in [0, 1]
        if x > 2.0:
            priority_score = 0.95
        elif x < -2.0:
            priority_score = 0.05
        else:
            # Polynomial approximation of sigmoid
            priority_score = 0.5 + (x / 5.0) + (x**3 / 20.0)
            priority_score = max(0.0, min(1.0, priority_score))
        
        return priority_score
    
    @classmethod
    def _generate_explanation(cls, elderly_count: int, infant_count: int,
                             pregnant_count: int, pwd_count: int,
                             priority_score: float, vulnerability_factors: list) -> str:
        """
        Generate a human-readable explanation of the priority score.
        
        Args:
            elderly_count: Number of elderly residents
            infant_count: Number of infants
            pregnant_count: Number of pregnant residents
            pwd_count: Number of PWD residents
            priority_score: Final priority score
            vulnerability_factors: List of vulnerability factors
        
        Returns:
            Human-readable explanation
        """
        
        priority_pct = int(priority_score * 100)
        
        parts = []
        parts.append(f"Household Vulnerability Assessment: {priority_pct}% priority")
        
        if not vulnerability_factors:
            parts.append("No identified vulnerability factors.")
        else:
            parts.append(f"Vulnerable members: {', '.join(vulnerability_factors)}.")
        
        # Priority level classification
        if priority_score < 0.2:
            priority_level = "Low"
        elif priority_score < 0.4:
            priority_level = "Moderate"
        elif priority_score < 0.7:
            priority_level = "High"
        else:
            priority_level = "Critical"
        
        parts.append(f"Priority level: {priority_level}")
        
        # Specific guidance
        if infant_count > 0:
            parts.append(f"Household has {infant_count} infant(s) requiring special evacuation support.")
        if elderly_count > 0:
            parts.append(f"Household has {elderly_count} elderly resident(s) who may need mobility assistance.")
        if pregnant_count > 0:
            parts.append(f"Household has {pregnant_count} pregnant resident(s) needing medical monitoring.")
        if pwd_count > 0:
            parts.append(f"Household has {pwd_count} resident(s) with disabilities requiring accommodations.")
        
        return " ".join(parts)
