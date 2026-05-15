# City-Wide Endpoint Implementation Report

## Overview
A new API endpoint `/api/v1/decision/city-wide` has been successfully implemented to provide city-wide disaster prioritization. This endpoint aggregates flood risk and resident vulnerability across all barangays using the existing Fuzzy Logic and AHP decision engine. It supports the frontend SmartFlood Command Center dashboard by supplying ranked, structured explainability data for auditing and UI rendering.

## How the Endpoint Works

1. **Routing (`POST /api/v1/decision/city-wide`)**: 
   - Receives the request and calls `DecisionService.make_city_wide_decision()`.
   - Returns a `CityWideAnalysisResponse` structured with an array of `CityWideAnalysisItem`s under `city_analysis`.
   - Includes graceful error handling; it returns an empty array instead of crashing if the top-level database fetch fails.

2. **Fetching Barangays (`app/database/supabase.py`)**:
   - `SupabaseConnection.get_all_barangays()` attempts to fetch all available barangays. 
   - First, it queries the `barangays` table for `id` and `name`. 
   - If that table doesn't exist or isn't accessible, it falls back to grabbing unique `barangay_id` values from the `residents` table.

3. **Orchestrating the Decision Engine (`app/services/decision_service.py`)**:
   - Loops through all fetched barangays.
   - For each barangay, it calls the existing `make_decision(barangay_id=...)` method to run the fuzzy logic assessment on MongoDB sensor data and the AHP prioritization on Supabase household demographics.
   - Any barangay that encounters a failure (e.g. missing records) is skipped/logged individually, ensuring the process completes for the rest of the city.

4. **Response Formatting and Ranking**:
   - Maps the individual results into the `CityWideAnalysisItem` schema.
   - Sorts the final list based on three criteria:
     1. **Risk Severity**: HIGH > MEDIUM > LOW
     2. **Confidence Score**: Descending (highest confidence first)
     3. **Vulnerability Index (Priority Score)**: Descending (most vulnerable first)
   - Outputs rich explainability features including `short_reason`, `detailed_reasoning` (with specific flood and vulnerability analysis), and the list of recommended actions.

## Frontend Connection Guide

To integrate this endpoint with your frontend dashboard, you can make a `POST` request.

### Example Fetch (Next.js / React)

```typescript
const fetchCityAnalysis = async () => {
  try {
    const res = await fetch("https://<your-api-url>/api/v1/decision/city-wide", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      }
    });

    if (!res.ok) throw new Error("Failed to fetch city-wide analysis");
    
    const data = await res.json();
    console.log("City-wide analysis:", data.city_analysis);
    
    // Example: Render the top priority barangay
    const topPriority = data.city_analysis[0];
    if (topPriority) {
        console.log(`Highest Priority: ${topPriority.barangay_name}`);
        console.log(`Risk Level: ${topPriority.risk_level}`);
        console.log(`Recommended Actions:`, topPriority.recommended_items);
    }
    
    return data.city_analysis;
  } catch (error) {
    console.error("Error fetching city-wide data:", error);
    return [];
  }
};
```

### Dashboard UI Considerations
- **Sorting is pre-applied**: The backend already handles the sorting logic (HIGH risk -> Confidence -> Vulnerability). You can safely render the list sequentially.
- **Dynamic Styling**: Use the `risk_level` ("HIGH", "MEDIUM", "LOW") to drive UI styling (e.g. red for HIGH, yellow for MEDIUM, green for LOW).
- **Explainability Modals**: The `detailed_reasoning` object contains rich narrative text (`flood_analysis`, `vulnerability_analysis`, etc.). You can show these fields in a "View Details" modal for transparency and auditing.
