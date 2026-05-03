# Example Requests and Responses

This file contains example API requests and responses for testing and reference.

## 1. Health Check

### Request

```bash
curl -X GET http://localhost:10000/health
```

### Response (200 OK)

```json
{
  "status": "healthy",
  "message": "AI Decision Service is running"
}
```

---

## 2. Decision Endpoint - Scenario 1: Low Risk, No Vulnerability

### Request

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'
```

**Assumption:**

- Sensor data: avg_water_level=30cm, max_water_level=35cm, trend=falling
- Household: 0 elderly, 0 infants, 0 pregnant, 0 PWD, 5 total residents

### Response (200 OK)

```json
{
  "barangay_id": 1,
  "risk_level": "LOW",
  "priority_score": 0.05,
  "recommended_action": "SAFE",
  "confidence_score": 0.85,
  "explanation": "Risk level LOW combined with low vulnerability (5%) suggests the area is currently safe with no urgent action needed (confidence: 85%). Recommendation: SAFE",
  "override_action": null,
  "fuzzy_explanation": "Average water level is 30.0cm, well below warning threshold. Water levels are FALLING, situation improving. Risk assessment: LOW (confidence: 90%)",
  "ahp_explanation": "Household Vulnerability Assessment: 5% priority. No identified vulnerability factors. Priority level: Low"
}
```

---

## 3. Decision Endpoint - Scenario 2: Medium Risk, Moderate Vulnerability

### Request

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 2}'
```

**Assumption:**

- Sensor data: avg_water_level=75cm, max_water_level=85cm, trend=stable
- Household: 1 elderly, 0 infants, 0 pregnant, 0 PWD, 6 total residents

### Response (200 OK)

```json
{
  "barangay_id": 2,
  "risk_level": "MEDIUM",
  "priority_score": 0.42,
  "recommended_action": "PREPARE",
  "confidence_score": 0.77,
  "explanation": "Risk level MEDIUM combined with moderate vulnerability (42%) warrants preparation for potential evacuation (confidence: 77%). Recommendation: PREPARE",
  "override_action": null,
  "fuzzy_explanation": "Average water level is 75.0cm, approaching caution threshold (50cm). Water levels are STABLE. Risk assessment: MEDIUM (confidence: 80%)",
  "ahp_explanation": "Household Vulnerability Assessment: 42% priority. Vulnerable members: Elderly (1). Priority level: Moderate. Household has 1 elderly resident(s) who may need mobility assistance."
}
```

---

## 4. Decision Endpoint - Scenario 3: High Risk, High Vulnerability

### Request

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 3}'
```

**Assumption:**

- Sensor data: avg_water_level=120cm, max_water_level=145cm, trend=rising
- Household: 2 elderly, 1 infant, 1 pregnant, 1 PWD, 7 total residents

### Response (200 OK)

```json
{
  "barangay_id": 3,
  "risk_level": "HIGH",
  "priority_score": 0.82,
  "recommended_action": "IMMEDIATE RELIEF",
  "confidence_score": 0.95,
  "explanation": "Risk level HIGH combined with high vulnerability (82%) indicates immediate relief is needed (confidence: 95%). Recommendation: IMMEDIATE RELIEF",
  "override_action": null,
  "fuzzy_explanation": "Average water level is 120.0cm, in danger zone (100-150cm). Water levels are RISING, situation deteriorating. Recent peak of 145.0cm indicates potential flooding risk. Risk assessment: HIGH (confidence: 95%)",
  "ahp_explanation": "Household Vulnerability Assessment: 82% priority. Vulnerable members: Elderly (2), Infants (1), Pregnant (1), PWD (1). Priority level: Critical. Household has 2 elderly resident(s) who may need mobility assistance. Household has 1 infant(s) requiring special evacuation support. Household has 1 pregnant resident(s) needing medical monitoring. Household has 1 resident(s) with disabilities requiring accommodations."
}
```

---

## 5. Error Scenario - Invalid Barangay ID

### Request

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": -1}'
```

### Response (400 Bad Request)

```json
{
  "detail": "barangay_id must be a positive integer"
}
```

---

## 6. Error Scenario - Invalid Request Body

### Request

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"invalid_field": "value"}'
```

### Response (422 Unprocessable Entity)

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "barangay_id"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

---

## Testing with Python

```python
import requests
import json

BASE_URL = "http://localhost:10000"

def test_health_check():
    """Test the health check endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    print("Health Check:")
    print(json.dumps(response.json(), indent=2))

def test_decision(barangay_id):
    """Test the decision endpoint"""
    payload = {"barangay_id": barangay_id}
    response = requests.post(f"{BASE_URL}/api/v1/decision", json=payload)
    print(f"\nDecision for Barangay {barangay_id}:")
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    test_health_check()
    test_decision(1)
    test_decision(2)
    test_decision(3)
```

---

## Testing with Python requests (Advanced)

```python
import requests
from typing import Dict, Any

class DecisionServiceClient:
    def __init__(self, base_url: str = "http://localhost:10000"):
        self.base_url = base_url
        self.session = requests.Session()

    def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def get_decision(self, barangay_id: int) -> Dict[str, Any]:
        """Get decision for a barangay"""
        response = self.session.post(
            f"{self.base_url}/api/v1/decision",
            json={"barangay_id": barangay_id}
        )
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the session"""
        self.session.close()

# Usage
client = DecisionServiceClient()

try:
    # Check health
    health = client.health_check()
    print(f"Service Status: {health['status']}")

    # Get decision
    decision = client.get_decision(barangay_id=1)
    print(f"Recommendation: {decision['recommended_action']}")
    print(f"Confidence: {decision['confidence_score']:.0%}")

finally:
    client.close()
```

---

## Performance Testing with Locust

```python
# locustfile.py
from locust import HttpUser, task, between
import json

class DecisionServiceUser(HttpUser):
    wait_time = between(1, 5)

    @task(1)
    def health_check(self):
        self.client.get("/health")

    @task(3)
    def get_decision(self):
        self.client.post(
            "/api/v1/decision",
            json={"barangay_id": 1}
        )

# Run with: locust -f locustfile.py --host=http://localhost:10000
```

---

## Integration Test Examples

```python
import pytest
import requests

@pytest.fixture
def api_url():
    return "http://localhost:10000"

def test_health_endpoint(api_url):
    response = requests.get(f"{api_url}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_decision_endpoint_valid_barangay(api_url):
    response = requests.post(
        f"{api_url}/api/v1/decision",
        json={"barangay_id": 1}
    )
    assert response.status_code == 200
    data = response.json()
    assert "risk_level" in data
    assert "priority_score" in data
    assert "recommended_action" in data
    assert "confidence_score" in data

def test_decision_endpoint_invalid_barangay(api_url):
    response = requests.post(
        f"{api_url}/api/v1/decision",
        json={"barangay_id": -1}
    )
    assert response.status_code == 400
    assert "positive integer" in response.json()["detail"]

def test_decision_response_schema(api_url):
    response = requests.post(
        f"{api_url}/api/v1/decision",
        json={"barangay_id": 1}
    )
    data = response.json()

    # Verify all required fields
    assert 0 <= data["priority_score"] <= 1
    assert 0 <= data["confidence_score"] <= 1
    assert data["recommended_action"] in ["SAFE", "PREPARE", "IMMEDIATE RELIEF"]
    assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH"]

# Run with: pytest -v
```

---

## Load Testing Response Times

Expected response times (local):

- Health check: ~5ms
- Decision request (with data): ~500ms - 2s (depends on DB speed)
- Cold start (first request): ~3-5s

On Render (free tier):

- Health check: ~50-100ms
- Decision request: ~1-3s
- Cold start: ~5-10s (may scale up if needed)
