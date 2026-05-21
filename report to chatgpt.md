# SmartFlood Human-in-the-Loop AI — Recalibration Report (for ChatGPT / stakeholders)

This document describes how the **SmartFlood** disaster response AI layer works **after** the May 2026 recalibration: fuzzy flood hazard, expanded AHP vulnerability, rule-based recommendations, and enriched API explainability. The deployment stack (**FastAPI**, **MongoDB Atlas**, **Supabase**, **Render**) is unchanged; only the **AI logic** and **response shape** were extended.

---

## 1. End-to-end flow (unchanged architecture)

1. **POST `/api/v1/decision`** with `{ "barangay_id": <int>, "override_action": null | "<action>" }`.
2. **MongoDB** `sensor_readings`: last *N* minutes aggregated to `avg_water_level` / `max_water_level` (cm), `trend`, optional **`rainfall_intensity_mm`** (average over the window if present on documents).
3. **Supabase** `residents` for the barangay: counts for vulnerability flags and ages.
4. **Fuzzy logic** produces `RiskLevel` plus a **public hazard label** (e.g. `LOW HAZARD (YELLOW)`).
5. **AHP-style weighted model** (seven factors, weights sum to 100%) yields `priority_score` ∈ [0, 1] and a full **audit trail**.
6. **Decision engine** merges hazard, trend, rainfall ratio to IDF, and vulnerability into **ranked, rule-based** `suggestions` (no black-box ML).
7. **Human-in-the-loop**: `override_action` still replaces the official recommendation while keeping AI suggestions advisory.

---

## 2. Flood engineering context (constants)

| Parameter | Value | Role in code |
|-----------|--------|----------------|
| IDF design rainfall | **243.100 mm** | `FuzzyLogicService.DESIGN_RAINFALL_MM` — scales how much observed rainfall intensifies MEDIUM/HIGH memberships. |
| 5-year return period framing | **~20% annual exceedance (1/5)** | `ANNUAL_EXCEEDANCE_PROBABILITY` — narrated in `reasoning_steps` / `engineering_context` (planning transparency, not a probability on the current reading). |

---

## 3. Recalibrated fuzzy logic (official hazard bands)

Depths are stored in **cm** in MongoDB; internally the service converts to **meters** for alignment with your hazard table.

| Official band | Depth (m) | Fuzzy engine |
|---------------|-----------|----------------|
| Below advisory flood stage | **&lt; 0.1** | Class stays **LOW**; label **SAFE / LOW** when the winning class is LOW and depth is under 0.1 m. |
| LOW HAZARD (YELLOW) | **0.1 – 0.5** | LOW membership dominant; descriptor **LOW HAZARD (YELLOW)** when appropriate. |
| MEDIUM HAZARD (ORANGE) | **0.5 – 1.5** | MEDIUM membership dominant; **MEDIUM HAZARD (ORANGE)**. |
| HIGH HAZARD (RED) | **&gt; 1.5** | HIGH membership dominant; **HIGH HAZARD (RED)**. |

### 3.1 Membership and fusion (summary)

- **Base memberships** are piecewise-linear in depth (m) for LOW, MEDIUM, HIGH, with **overlap** between bands so transitions are gradual.
- **Peak fusion**: memberships from average depth and max depth are combined with a **fuzzy OR** so short spikes are visible but do not alone invent impossible states.
- **Trend**: rising nudges mass toward higher classes; falling nudges toward lower (bounded, then renormalized).
- **Rainfall**: intensity (mm) is compared to the **243.1 mm** reference; heavy rain nudges MEDIUM/HIGH up and LOW down (bounded, renormalized).
- **Dry-stage guardrail**: if **both** average and peak depth ≤ **0.10 m**, the class is forced to **LOW** so **0.0 m never yields HIGH** even under extreme rainfall input (rain still appears in reasoning for operators).

### 3.2 Confidence (deterministic)

Derived from the **renormalized “posterior”** over {LOW, MEDIUM, HIGH}: strength of the winner and margin to the runner-up, with small adjustments for stable trend vs spike divergence vs very high rainfall.

### 3.3 Validated examples (stable, no rain)

| Depth | Expected label (winner) |
|-------|-------------------------|
| 0.0 m | **SAFE / LOW**, `RiskLevel.LOW` |
| 0.2 m | **LOW HAZARD (YELLOW)**, `RiskLevel.LOW` |
| 0.8 m | **MEDIUM HAZARD (ORANGE)**, `RiskLevel.MEDIUM` |
| 1.8 m | **HIGH HAZARD (RED)**, `RiskLevel.HIGH` |

*(Automated in `tests/test_smartflood_calibration.py`.)*

---

## 4. AHP vulnerability expansion (seven factors, 100% weights)

`priority_score = Σ weight_i × factor_score_i` with each `factor_score_i` ∈ [0, 1] from resident proportion × category multiplier. **No sigmoid** — the index is fully transparent.

| Factor | Weight | Rationale (also in API `factor_rationale`) |
|--------|--------|---------------------------------------------|
| Infant | **22%** | Complete dependence; contamination / hypothermia risk. |
| Elderly | **20%** | Mobility and chronic illness; slower evacuation. |
| PWD | **18%** | Assistive needs, accessible routes, injury risk in debris flows. |
| Pregnant | **12%** | Antenatal strain and need for medical continuity. |
| Lactating mother | **10%** | Infant feeding continuity during displacement. |
| Solo parent | **10%** | Single caregiver bottleneck during move-out. |
| 4Ps beneficiary | **8%** | Transport / cash constraints delay self-evacuation. |

**Total = 100%.** Higher counts (relative to `total_residents`) raise `priority_score`; households with many overlapping vulnerabilities rank higher for relief — as intended.

### 4.1 Supabase / `residents` fields (optional, backward compatible)

If columns are absent, counts default to **0**. Supported truthy keys include:

- **4Ps**: `is_4ps`, `is_four_ps`, `four_ps`, `is_4ps_beneficiary`
- **Lactating**: `is_lactating`, `lactating`
- **Solo parent**: `is_solo_parent`, `solo_parent`

Existing: `age`, `is_pregnant`, `is_pwd`.

---

## 5. Recommendation engine (post-calibration)

Recommendations are still **pure rules**. New / emphasized actions:

- **`FULL EVACUATION`** — top urgency when **HIGH** hazard, **rising** trend, **high** vulnerability, and either **catastrophic depth** (≥ ~1.65 m average depth in the fuzzy payload) **or** **heavy rainfall** vs IDF (ratio ≥ ~0.72). Additional rule for **HIGH + rising + moderate vulnerability + catastrophic depth**.

Other actions remain: **SAFE**, **MONITOR**, **PREPARE**, **PREPARE FOOD PACKS**, **DEPLOY RESCUE TEAM**, **PARTIAL EVACUATION**, **IMMEDIATE RELIEF**, plus existing logistics / medical actions. Urgency scores were tuned so **FULL EVACUATION** can outrank **IMMEDIATE RELIEF** only in the catastrophic conjunctions above.

Rules explicitly reference **hazard class**, **trend**, **rainfall ratio to 243.1 mm**, and **vulnerability index** in their natural-language `reason` strings.

---

## 6. Explainability in the API

`DecisionResponse` now includes three optional structured blocks (populated on success paths; `null` on hard error fallback):

1. **`fuzzy_assessment`** — `FuzzyAssessmentDetail`: hazard label, depths (m), trend, rainfall input, memberships, `reasoning_steps`.
2. **`ahp_breakdown`** — `AHPPriorityBreakdown`: `weights_percent`, `weighted_contributions`, `sub_scores`, `breakdown_lines`, `factor_rationale`, `vulnerability_factors`.
3. **`explainability`** — `ExplainabilityPayload`: narrative strings `why_flood_risk_classified`, `why_barangay_priority`, and `top_recommendations_explained` (each line lists **drivers**: hazard, trend, rain, vulnerability index).

Legacy string fields **`fuzzy_explanation`** and **`ahp_explanation`** remain for backward compatibility.

---

## 7. Example API response (illustrative JSON)

> Values depend on live DB; this shape matches the new Pydantic models.

```json
{
  "barangay_id": 99,
  "risk_level": "HIGH",
  "priority_score": 0.72,
  "suggestions": [
    {
      "priority_rank": 1,
      "action": "FULL EVACUATION",
      "confidence_score": 0.94,
      "reason": "Depth near or above official HIGH band with rising trend and concentrated vulnerability; intense rainfall vs IDF design further stresses drainage — area-wide evacuation is the realistic protective action"
    }
  ],
  "recommended_action": "FULL EVACUATION",
  "confidence_score": 0.94,
  "explanation": "Risk level HIGH combined with high vulnerability (72%) supports coordinated full evacuation as the top rule-based action …",
  "override_action": null,
  "fuzzy_explanation": "SmartFlood fuzzy assessment: HIGH HAZARD (RED) …",
  "ahp_explanation": "Household / barangay vulnerability index: 72/100 …",
  "fuzzy_assessment": {
    "hazard_descriptor": "HIGH HAZARD (RED)",
    "risk_level": "HIGH",
    "depth_avg_m": 1.7,
    "depth_max_m": 1.7,
    "trend": "rising",
    "rainfall_intensity_mm": 200.0,
    "confidence_score": 0.91,
    "membership_scores": {"LOW": 0.0, "MEDIUM": 0.0, "HIGH": 1.0},
    "reasoning_steps": ["Converted sensor depth: …", "…"]
  },
  "ahp_breakdown": {
    "priority_score": 0.72,
    "weights_percent": {"infant": 22.0, "elderly": 20.0, "pwd": 18.0, "pregnant": 12.0, "lactating": 10.0, "solo_parent": 10.0, "four_ps": 8.0},
    "weighted_contributions": {},
    "sub_scores": {},
    "breakdown_lines": ["infant: weight 22.00% × factor …"],
    "vulnerability_factors": ["PWD (3)", "Infant (4)", "…"],
    "factor_rationale": {"infant": "…", "elderly": "…"}
  },
  "explainability": {
    "why_flood_risk_classified": "Hazard label «HIGH HAZARD (RED)» corresponds to fuzzy class HIGH with average depth 1.70 m, trend rising, rainfall 200.0 mm, and posterior weights …",
    "why_barangay_priority": "… Contribution audit: …",
    "top_recommendations_explained": [
      "Rank 1 — FULL EVACUATION: …. Drivers: hazard=HIGH, trend=rising, rain=200.0 mm, vulnerability_index=0.72."
    ]
  }
}
```

---

## 8. Validation

- **Tests**: `pytest tests/test_smartflood_calibration.py -q` (requires deps from `requirements.txt`; repo includes `pytest.ini` with `pythonpath = .`).
- **Health**: `GET /health` and `GET /api/v1/health` return 200 when the process is up (DB failures on startup are logged but the app can still serve health checks).

---

## 9. Recommendation calibration summary

| Signal | Effect |
|--------|--------|
| **Hazard class** (LOW / MEDIUM / HIGH) | Sets the baseline action tier (safe/monitor vs prepare vs rescue/evacuation). |
| **Trend** | Rising unlocks stronfinal-working-allowed-origin-vercelger evacuation and faster relief; falling dampens fuzzy HIGH mass. |
| **Rainfall vs 243.1 mm** | Heavy rain strengthens MEDIUM/HIGH memberships and raises urgency of food packs, resources, and evacuation rules. |
| **Vulnerability index** | Gates **IMMEDIATE RELIEF**, **MEDICAL**, **FULL EVACUATION** conjunctions; high index prioritizes in-place assistance when hydrology is borderline. |

---

## 10. Operational note

All outputs remain **auditable rules**. Operators should continue to use **`override_action`** when field conditions disagree with sensors or registry data — the API is designed for **human-in-the-loop** governance, not autonomous execution.

---

*Generated as part of the SmartFlood recalibration implementation.*
