"""
Configurable operational constants for the relief recommendation engine.
These constants govern scaling logic for resources and other deterministic estimations.
"""

# Demographic Constants
AVERAGE_HOUSEHOLD_SIZE = 5

# Resource Scaling Constants (multipliers per affected family/individual)
FOOD_PACK_SCALING = 0.7  # Food packs per affected family
WATER_SCALING = 2.0      # Liters of water per affected family
MEDICINE_SCALING = 0.2   # Medicine kits per vulnerable individual
HYGIENE_SCALING = 0.3    # Hygiene kits per vulnerable individual
BLANKET_SCALING = 0.5    # Blankets per evacuated individual

# Estimation Thresholds
EVACUATION_PARTIAL_RATIO = 0.2  # 20% of affected might evacuate initially
EVACUATION_FULL_RATIO = 0.8     # 80% of affected might evacuate under HIGH/CRITICAL

# Operational Urgency Thresholds
URGENCY_CRITICAL_MIN = 85
URGENCY_HIGH_MIN = 60
URGENCY_MEDIUM_MIN = 35
