# Latest implementation — three suggestions and changed version

**Document purpose:** Snapshot of the current Human-in-the-Loop AI FastAPI service: how many suggestions it returns, and what changed in the recent “deployment-ready / Python 3.11” pass.

---

## Does this project return three suggestions?

**Yes.** The API is designed so every successful `/api/v1/decision` response includes **at least three** ranked suggestions.

| Mechanism | Location |
|-----------|----------|
| Minimum count constant | `app/services/decision_service.py` — `MIN_SUGGESTIONS = 3` |
| Padding / fallbacks | Same file — `_pad_to_minimum`, `_error_fallback_suggestions` ensure the list is never shorter than three |
| API contract | `app/models/schemas.py` — `DecisionResponse.suggestions` has `min_length=3` |

**Upper bound:** The ranked list passed to the client is capped at **eight** suggestions (`final = padded[:8]` in `DecisionService._build_ranked_suggestions`). So you get **3–8** suggestions, never fewer than three.

Each suggestion includes `priority_rank`, `action`, `confidence_score`, and `reason` (see `Suggestion` in `schemas.py`).

---

## “Changed version” — stack and behavior (summary)

### Application version (API)

- FastAPI app metadata in `app/main.py`: **`version="1.0.0"`** (unchanged semantic version; behavior and infra were hardened).

### Dependency pins (`requirements.txt`)

| Package | Version (current file) |
|---------|-------------------------|
| fastapi | 0.115.5 |
| uvicorn[standard] | 0.32.1 |
| pydantic | 2.9.2 |
| pymongo | 4.6.0 |
| supabase | 2.15.1 |
| python-dotenv | 1.0.0 |

**Why these bumps matter:** Newer **Supabase** client aligns with current **httpx** (fixes older `proxy` / client init issues on deploy). **FastAPI** / **Starlette** were raised to stay compatible with that **httpx** line. Target runtime remains **Python 3.11.9** (`runtime.txt`).

### Notable implementation / ops changes

- **`GET /health`** at the app root for load balancers and docs (in addition to **`GET /api/v1/health`**).
- **Trusted hosts:** safer defaults for Render (`*.onrender.com`), optional merges when `RENDER=true` or `ENV=development` (e.g. `testserver` for tests).
- **CORS:** `ALLOWED_ORIGINS` entries are trimmed; empty list falls back to localhost.
- **Startup logging:** Python runtime version logged at startup.
- **Bugfix:** `stable` trend variable was undefined in `_collect_rule_candidates` (HIGH + stable path) — fixed.
- **`render.yaml`:** Blueprint for web service using `$PORT` with Uvicorn.
- **`app/__init__.py`:** Package marker added.
- **`.gitignore`:** `render.yaml` is no longer ignored so it can be committed.

### Core logic unchanged

- Fuzzy flood risk, AHP vulnerability scoring, human **override** on decisions, and the **rule-based multi-suggestion** engine are the same product design; only compatibility, deployment, and the `stable` bugfix touched execution paths.

---

## Quick verification commands

```bash
# From project root, with venv activated
uvicorn app.main:app --host 0.0.0.0 --port 10000
```

```bash
curl -s http://localhost:10000/health
curl -s -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'
```

Inspect the JSON: `suggestions` should be an array of **at least three** objects.

---

*Generated to match the repository state when this file was added.*
