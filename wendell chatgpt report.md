# Wendell ChatGPT Report

## System Overview

This project is a FastAPI-based AI Decision Service for flood disaster management. Its main purpose is to help operators decide what action to take for a barangay by combining two kinds of information:

1. Flood hazard information from sensor readings stored in MongoDB.
2. Household or resident vulnerability information stored in Supabase.

The system is designed as a human-in-the-loop decision support service. That means the AI produces ranked recommendations and explanations, but a human operator can still override the final action when needed.

The service is not a black-box machine learning model. It uses transparent, rule-based reasoning:

- Fuzzy logic for flood risk assessment.
- AHP-style weighted scoring for vulnerability assessment.
- Rule-based ranking for operational recommendations.

## Main Application Flow

The application starts from `app/main.py`. When the FastAPI server starts, it loads environment variables from `.env`, configures logging, sets up CORS and trusted host middleware, and tries to connect to both databases:

- `MongoDBConnection.connect()` for MongoDB Atlas.
- `SupabaseConnection.connect()` for Supabase PostgreSQL.

The API routes are registered under `/api/v1`. The main decision endpoint is:

```http
POST /api/v1/decision
```

The request body looks like this:

```json
{
  "barangay_id": 1
}
```

Optionally, a human operator can provide an override:

```json
{
  "barangay_id": 1,
  "override_action": "IMMEDIATE RELIEF"
}
```

When a request arrives, the route in `app/routes/decision.py` validates that `barangay_id` is a positive integer. Then it calls:

```python
DecisionService.make_decision(...)
```

That service is the central decision engine.

## Database Fetch: MongoDB Sensor Data

MongoDB is used for flood sensor readings. The connection logic is in:

```text
app/database/mongodb.py
```

The service reads the MongoDB connection string from:

```env
MONGODB_URI
```

It can also use:

```env
MONGODB_DB
```

if a specific database name is configured.

The decision engine calls:

```python
MongoDBConnection.get_sensor_data(barangay_id, minutes=10)
```

This fetches recent sensor readings from the `sensor_readings` collection for the selected barangay. It only looks at readings from the latest time window, normally the last 10 minutes.

The query filters by:

- `barangay_id`
- `timestamp >= current_time - 10 minutes`

The readings are sorted by timestamp from oldest to newest. From these readings, the system calculates:

- `avg_water_level`: average water level in centimeters.
- `max_water_level`: highest recent water level in centimeters.
- `trend`: whether the water is `rising`, `falling`, or `stable`.
- `rainfall_intensity_mm`: average rainfall value if rainfall fields exist.
- `readings_count`: number of readings used.

The trend is calculated by splitting the water readings into two halves:

- First half average.
- Second half average.

If the second half is more than 2% higher than the first half, the trend is `rising`. If it is more than 2% lower, the trend is `falling`. Otherwise, the trend is `stable`.

If no sensor readings are found, MongoDB returns a safe fallback:

```json
{
  "avg_water_level": 0.0,
  "max_water_level": 0.0,
  "trend": "stable",
  "rainfall_intensity_mm": 0.0,
  "readings_count": 0
}
```

This prevents the service from immediately crashing just because a barangay has no recent sensor data.

## Database Fetch: Supabase Resident Data

Supabase is used for household and resident vulnerability data. The connection logic is in:

```text
app/database/supabase.py
```

The service reads Supabase credentials from:

```env
SUPABASE_URL
SUPABASE_KEY
```

The decision engine calls:

```python
SupabaseConnection.get_household_vulnerability(barangay_id)
```

This fetches rows from the `residents` table where:

```text
barangay_id = requested barangay
```

From those residents, the service counts vulnerability categories:

- `elderly_count`: residents age 60 or above.
- `infant_count`: residents age 2 or below.
- `pregnant_count`: residents marked as pregnant.
- `pwd_count`: residents marked as persons with disabilities.
- `four_ps_count`: residents marked as 4Ps beneficiaries.
- `lactating_count`: lactating mothers.
- `solo_parent_count`: solo parents.
- `total_residents`: total residents found for that barangay.

The service accepts several possible column names for some categories. For example, 4Ps may be detected from fields like:

- `is_4ps`
- `is_four_ps`
- `four_ps`
- `is_4ps_beneficiary`

If no residents are found, Supabase returns all vulnerability counts as zero.

## Fuzzy Logic Reasoning

The fuzzy logic service is in:

```text
app/services/fuzzy_service.py
```

Its job is to classify flood hazard into:

- `LOW`
- `MEDIUM`
- `HIGH`

The input values are:

- Average water level from MongoDB.
- Maximum water level from MongoDB.
- Water trend from MongoDB.
- Rainfall intensity from MongoDB, if available.

MongoDB stores water level in centimeters, but the fuzzy service converts it internally to meters.

The hazard bands are:

| Flood Depth | Meaning |
|---|---|
| Below 0.10 m | Safe / low stage |
| 0.10 m to 0.50 m | Low hazard, yellow |
| 0.50 m to 1.50 m | Medium hazard, orange |
| Above 1.50 m | High hazard, red |

The fuzzy logic does not simply use one hard threshold. Instead, it calculates membership scores for `LOW`, `MEDIUM`, and `HIGH`. This is useful because flood conditions can sit near a boundary. For example, a water level near 0.50 m might partially belong to both low and medium risk.

The system calculates memberships for:

- Average depth.
- Recent peak depth.

Then it combines them using a fuzzy OR-style operation, so a recent spike is not ignored.

After the depth membership is calculated, the system adjusts it using trend:

- Rising water increases medium and high risk.
- Falling water reduces high risk and slightly supports low risk.
- Stable water keeps the membership mostly unchanged.

Rainfall also adjusts the membership. The system compares rainfall against a design rainfall reference of:

```text
243.100 mm
```

Higher rainfall increases hydrologic stress and slightly pushes the assessment toward medium or high risk.

After all adjustments, the membership values are normalized into a probability-like distribution:

```json
{
  "LOW": 0.10,
  "MEDIUM": 0.25,
  "HIGH": 0.65
}
```

The class with the highest value becomes the final `risk_level`.

The fuzzy service also calculates a confidence score. Confidence is based on:

- How strong the winning class is.
- How far the winning class is from the second-highest class.
- Whether the trend and peak readings introduce uncertainty.
- Whether rainfall is very high.

There is also a dry-stage guardrail. If both average and peak depth are at or below 0.10 m, the result is forced to `LOW`. This prevents noisy dry sensors from producing a false high-risk classification.

The fuzzy output includes:

- `risk_level`
- `confidence_score`
- `hazard_descriptor`
- `membership_scores`
- `reasoning_steps`
- `fuzzy_explanation`

This makes the flood-risk decision explainable to a human reviewer.

## AHP-Style Vulnerability Reasoning

The vulnerability service is in:

```text
app/services/ahp_service.py
```

Its job is to calculate a `priority_score` from 0 to 1 based on vulnerable population groups.

The system uses seven factors:

| Factor | Weight |
|---|---:|
| Infant | 22% |
| Elderly | 20% |
| PWD | 18% |
| Pregnant | 12% |
| Lactating mother | 10% |
| Solo parent | 10% |
| 4Ps beneficiary | 8% |

The weights sum to 100%. Each factor is converted into a score between 0 and 1 based on the count and total residents.

The formula works like this:

1. Count residents in each vulnerability category.
2. Divide each count by total residents to get the proportion.
3. Apply a multiplier based on severity or operational difficulty.
4. Clamp the factor score between 0 and 1.
5. Multiply each factor score by its weight.
6. Sum all weighted contributions.

The final result is:

```text
priority_score = sum(weight_i * factor_score_i)
```

The factor multipliers are:

| Factor | Multiplier |
|---|---:|
| Infant | 3.0 |
| Elderly | 2.5 |
| PWD | 2.4 |
| Pregnant | 1.6 |
| Lactating | 1.7 |
| Solo parent | 1.8 |
| 4Ps beneficiary | 1.5 |

This means a barangay with a high concentration of infants, elderly residents, PWD residents, or other vulnerable categories will receive a higher priority score.

The AHP output includes:

- `priority_score`
- `sub_scores`
- `weighted_contributions`
- `weights_percent`
- `vulnerability_factors`
- `factor_rationale`
- `breakdown_lines`
- `ahp_explanation`

This allows the system to explain not only the final score, but also which groups contributed most to the vulnerability priority.

## Decision Engine: Combining Risk and Vulnerability

The central decision engine is in:

```text
app/services/decision_service.py
```

The decision engine performs these steps:

1. Fetch recent flood sensor data from MongoDB.
2. Run fuzzy logic to classify flood hazard.
3. Fetch resident vulnerability data from Supabase.
4. Run AHP-style scoring to calculate priority.
5. Generate rule-based recommendation candidates.
6. Rank the candidates by urgency and confidence.
7. Return at least three suggestions.
8. Choose the top-ranked suggestion as the official recommendation unless a human override is provided.

The vulnerability score is interpreted using these thresholds:

| Priority Score | Meaning |
|---:|---|
| 0.65 and above | High vulnerability |
| 0.35 to below 0.65 | Medium vulnerability |
| Below 0.35 | Low vulnerability |

The decision engine has a rule candidate system. Each rule can add a possible action with:

- Action name.
- Reason.
- Urgency value.
- Confidence score.

Possible actions include:

- `SAFE`
- `MONITOR`
- `PREPARE`
- `PREPARE ADDITIONAL RESOURCES`
- `PREPARE FOOD PACKS`
- `PARTIAL EVACUATION`
- `IMMEDIATE RELIEF`
- `DEPLOY RESCUE TEAM`
- `SEND MEDICAL ASSISTANCE`
- `FULL EVACUATION`

Example rule logic:

- If risk is `HIGH`, trend is rising, vulnerability is high, and depth or rainfall is severe, the system may recommend `FULL EVACUATION`.
- If risk is `HIGH` and vulnerability is high, the system may recommend `IMMEDIATE RELIEF`.
- If risk is `HIGH`, the system may recommend `DEPLOY RESCUE TEAM`.
- If risk is `MEDIUM` and vulnerability is high, it may still recommend `IMMEDIATE RELIEF`.
- If risk is `LOW` but vulnerability is high, it may recommend `PREPARE`.
- If risk is `LOW` and vulnerability is not high, it may recommend `SAFE` and `MONITOR`.

After collecting rule candidates, the system deduplicates them. If the same action is suggested by multiple rules, the engine keeps the version with the highest urgency and confidence.

Then it sorts by:

1. Highest urgency.
2. Highest confidence.

The response always includes at least three suggestions. If the rules do not produce enough suggestions, the system pads the list using conservative fallback actions such as `PREPARE`, `MONITOR`, or `PREPARE ADDITIONAL RESOURCES`.

## Human-in-the-Loop Override

The system supports human override through the `override_action` field.

If no override is provided, the top-ranked AI suggestion becomes the official recommendation.

If an override is provided, that human-selected action becomes the official `recommended_action`. The AI suggestions are still returned, but they are advisory only.

This is important because emergency response decisions may need human judgment from field reports, local knowledge, road conditions, shelter availability, or political and operational constraints that are not yet in the database.

## API Response Structure

The decision endpoint returns a structured response containing both the final recommendation and the reasoning behind it.

Important response fields include:

```json
{
  "barangay_id": 1,
  "risk_level": "HIGH",
  "priority_score": 0.72,
  "suggestions": [
    {
      "priority_rank": 1,
      "action": "IMMEDIATE RELIEF",
      "confidence_score": 0.91,
      "reason": "HIGH hazard class with high vulnerability index..."
    }
  ],
  "recommended_action": "IMMEDIATE RELIEF",
  "confidence_score": 0.91,
  "explanation": "Risk level HIGH combined with high vulnerability...",
  "override_action": null,
  "fuzzy_explanation": "...",
  "ahp_explanation": "...",
  "fuzzy_assessment": {},
  "ahp_breakdown": {},
  "explainability": {}
}
```

The `fuzzy_assessment` field contains the structured flood-risk reasoning:

- Hazard descriptor.
- Risk level.
- Average and peak depth in meters.
- Trend.
- Rainfall intensity.
- Confidence score.
- Membership scores.
- Reasoning steps.

The `ahp_breakdown` field contains the structured vulnerability reasoning:

- Priority score.
- Weights.
- Weighted contributions.
- Sub-scores.
- Vulnerability factors.
- Factor rationale.

The `explainability` field connects the flood risk, vulnerability score, and final suggestions in human-readable language.

## City-Wide Decision Flow

The system also supports:

```http
POST /api/v1/decision/city-wide
```

This endpoint evaluates all barangays found in Supabase.

The flow is:

1. Try to fetch barangays from the `barangays` table.
2. If that table is unavailable, collect distinct `barangay_id` values from the `residents` table.
3. Run the normal decision pipeline for each barangay.
4. Sort barangays by risk, confidence, and vulnerability priority.
5. Return a ranked city-wide analysis.

This helps operators see which barangays should be prioritized first across the whole city.

## Error Handling and Fallback Behavior

The system is built to keep responding even when some data is missing.

If the application cannot connect to MongoDB or Supabase during startup, it logs the error but continues running. This keeps the health endpoint available.

If no MongoDB sensor readings are found for a barangay, the system uses safe default sensor values.

If no Supabase residents are found for a barangay, the system uses zero vulnerability counts.

If an unexpected error occurs inside the decision pipeline, the decision service returns a conservative fallback:

- Risk level: `MEDIUM`
- Priority score: `0.5`
- Recommended action: `PREPARE`
- Confidence score: low
- At least three fallback suggestions

This means the system fails in a cautious direction instead of silently saying everything is safe.

## Why the System Is Explainable

The system is explainable because every stage produces readable reasoning:

- MongoDB aggregation explains the water average, peak, trend, rainfall, and number of readings.
- Fuzzy logic explains the hazard band, membership scores, confidence, and reasoning steps.
- AHP explains the vulnerability counts, weights, sub-scores, and weighted contributions.
- The decision engine explains why each ranked suggestion was produced.
- Human override is explicitly shown when applied.

This is appropriate for disaster response because operators need to understand why a recommendation was made before acting on it.

## Summary

In simple terms, the system works like this:

1. The user sends a barangay ID to the API.
2. The system fetches recent water and rainfall readings from MongoDB.
3. The system calculates flood risk using fuzzy logic.
4. The system fetches resident data from Supabase.
5. The system calculates vulnerability using AHP-style weighted scoring.
6. The system combines flood hazard and vulnerability using transparent rules.
7. The system returns ranked actions, confidence scores, and explanations.
8. A human operator may override the final recommendation if needed.

The result is a practical human-in-the-loop AI service: automated enough to help prioritize quickly during flood events, but transparent enough for human review and responsible emergency decision-making.
