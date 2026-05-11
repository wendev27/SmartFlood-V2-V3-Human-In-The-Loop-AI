# Project Summary and Review Guide

## 1. Project Overview

This project is a disaster management decision support system built with FastAPI. It uses explainable AI techniques (Fuzzy Logic and Analytic Hierarchy Process/AHP) to assess flood risk and prioritize response actions for different barangays (communities). The system integrates real-world data from MongoDB (sensor readings) and Supabase (resident demographics) to make transparent, rule-based decisions.

## 2. Main Features
- **API Endpoints**: Exposes endpoints for health checks and decision-making (see `/api/v1/decision`).
- **Explainable AI**: Uses Fuzzy Logic for risk assessment and AHP for vulnerability scoring, with clear explanations in every response.
- **Human-in-the-loop**: Designed for human review and override, not black-box ML.
- **Cloud-ready**: Easily deployable to platforms like Render.

## 3. How the System Works
1. **User/API Client** sends a POST request to `/api/v1/decision` with a `barangay_id`.
2. **Backend** fetches:
   - Latest water level sensor data from MongoDB.
   - Resident demographic data from Supabase.
3. **Fuzzy Logic Module** ([app/services/fuzzy_service.py]):
   - Inputs: Average water level, max water level, trend.
   - Uses defined thresholds (e.g., 50cm, 100cm, 150cm) to classify risk as LOW, MEDIUM, or HIGH.
   - Outputs: Risk level and confidence score.
4. **AHP Module** ([app/services/ahp_service.py]):
   - Inputs: Counts of infants, elderly, pregnant, and PWD residents.
   - Applies weights (Infants 40%, Elderly 35%, Pregnant 15%, PWD 10%) to compute a priority score (0-1).
5. **Decision Engine** ([app/services/decision_service.py]):
   - Combines risk and priority to recommend an action:
     - HIGH risk & priority ≥ 0.65 → IMMEDIATE RELIEF
     - HIGH risk or priority ≥ 0.35 → PREPARE
     - Otherwise → SAFE
   - Returns explanations for all logic steps.

## 4. How Fuzzy Logic Works
- Fuzzy logic handles uncertainty in sensor data.
- It uses membership functions to assign degrees of risk (e.g., a water level of 120cm might be 0.7 MEDIUM and 0.3 HIGH).
- The system aggregates these to produce a final risk level and a confidence score.

## 5. How AHP Works
- AHP (Analytic Hierarchy Process) is a structured technique for organizing and analyzing complex decisions.
- Each vulnerable group (infants, elderly, pregnant, PWD) is assigned a weight.
- The system multiplies the count of each group by its weight, sums them, and normalizes to get a priority score (0-1).

## 6. What to Review for Thesis/Project Defense
- **Key Files**:
  - [app/main.py]: FastAPI app entry point
  - [app/models/schemas.py]: Data models
  - [app/services/fuzzy_service.py]: Fuzzy logic implementation
  - [app/services/ahp_service.py]: AHP implementation
  - [app/services/decision_service.py]: Decision logic
  - [app/routes/decision.py]: API endpoints
- **How to Run**: See QUICK_REFERENCE.md for setup, running, and testing instructions.
- **API Usage**: Know how to test endpoints with curl or Python.
- **Explainability**: Be ready to explain how/why the system makes each decision (see explanations in API responses).
- **No Blockchain**: The project does not use blockchain or smart contracts.
- **Deployment**: Understand how to deploy to Render or similar platforms.

## 7. Common Questions to Prepare For
- Why use rule-based AI instead of machine learning?
- How does fuzzy logic handle uncertainty?
- How are AHP weights chosen?
- How can a human override the system?
- How is data stored and accessed?
- How is the system secured (e.g., environment variables for secrets)?

---

**This file is your quick review guide for the project.**
