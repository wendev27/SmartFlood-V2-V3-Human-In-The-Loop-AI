# AI Decision Service - Flood Disaster Management Platform

A production-ready FastAPI microservice for human-in-the-loop AI decision making in flood disaster management. Uses **Fuzzy Logic** for risk assessment and **AHP (Analytic Hierarchy Process)** for household vulnerability evaluation.

## 🎯 Features

- **Explainable AI**: Rule-based fuzzy logic and AHP (no black-box models)
- **Real-time Data Integration**:
  - MongoDB Atlas for sensor data (water levels)
  - Supabase PostgreSQL for household demographics
- **Dual Assessment**:
  - Fuzzy Logic: Evaluates flood risk based on water levels and trends
  - AHP: Calculates household vulnerability based on vulnerable members
- **Human-in-the-Loop**: Support for human override of AI recommendations
- **Production-Ready**:
  - Type hints and Pydantic validation
  - Comprehensive logging
  - Error handling
  - CORS and security middleware

## 📁 Project Structure

```
app/
├── main.py                 # FastAPI app entry point
├── models/
│   ├── __init__.py
│   └── schemas.py          # Pydantic models for request/response
├── routes/
│   ├── __init__.py
│   └── decision.py         # API endpoint handlers
├── services/
│   ├── __init__.py
│   ├── fuzzy_service.py    # Fuzzy logic risk assessment
│   ├── ahp_service.py      # AHP vulnerability scoring
│   └── decision_service.py # Combined decision engine
└── database/
    ├── __init__.py
    ├── mongodb.py          # MongoDB Atlas integration
    └── supabase.py         # Supabase PostgreSQL integration
requirements.txt           # Python dependencies
runtime.txt               # Python version for deployment
.env.example              # Environment variables template
```

## 🚀 Quick Start - Local Development

### Prerequisites

- Python 3.10 or higher
- MongoDB Atlas account (free tier available)
- Supabase account (free tier available)
- Git

### Setup Steps

1. **Clone and navigate to project**

   ```bash
   cd "Human in the loop AI"
   ```

2. **Create Python virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your credentials:

   ```env
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/disaster_management?retryWrites=true
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-key
   ```

5. **Setup MongoDB Atlas** (if not already done)
   - Create free cluster at https://www.mongodb.com/cloud/atlas
   - Create database named `disaster_management`
   - Create collection: `sensor_readings`
   - Sample document structure:
     ```json
     {
       "barangay_id": 1,
       "water_level": 65.5,
       "timestamp": ISODate("2024-05-03T10:30:00Z")
     }
     ```

6. **Setup Supabase** (if not already done)
   - Create project at https://supabase.com
   - Create table `residents`:
     ```sql
     CREATE TABLE residents (
       id SERIAL PRIMARY KEY,
       barangay_id INTEGER NOT NULL,
       age INTEGER,
       is_pregnant BOOLEAN DEFAULT FALSE,
       is_pwd BOOLEAN DEFAULT FALSE,
       created_at TIMESTAMP DEFAULT NOW()
     );
     ```

7. **Run the development server**

   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 10000
   ```

   Server will be available at: `http://localhost:10000`

8. **Access API documentation**
   - Swagger UI: http://localhost:10000/docs
   - ReDoc: http://localhost:10000/redoc

## 📡 API Endpoints

### Health Check

```http
GET /health
```

Response:

```json
{
  "status": "healthy",
  "message": "AI Decision Service is running"
}
```

### Get Decision

```http
POST /api/v1/decision
Content-Type: application/json

{
  "barangay_id": 1
}
```

Response:

```json
{
  "barangay_id": 1,
  "risk_level": "HIGH",
  "priority_score": 0.82,
  "recommended_action": "IMMEDIATE RELIEF",
  "confidence_score": 0.85,
  "explanation": "High water level (120cm) with rising trend and vulnerable household members (2 elderly, 1 infant) indicate immediate relief is needed (confidence: 85%).",
  "override_action": null,
  "fuzzy_explanation": "Average water level is 120.0cm, in danger zone (100-150cm). Water levels are RISING, situation deteriorating. Risk assessment: HIGH (confidence: 95%)",
  "ahp_explanation": "Household Vulnerability Assessment: 82% priority. Vulnerable members: Elderly (2), Infants (1). Priority level: Critical. Household has 2 elderly resident(s) who may need mobility assistance. Household has 1 infant(s) requiring special evacuation support."
}
```

## 🔧 Testing Locally

### Using curl

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'
```

### Using Python requests

```python
import requests

response = requests.post(
    "http://localhost:10000/api/v1/decision",
    json={"barangay_id": 1}
)
print(response.json())
```

### Using FastAPI Docs

Navigate to http://localhost:10000/docs and use the interactive Swagger UI.

## 🧠 Algorithm Explanation

### Fuzzy Logic Module (`fuzzy_service.py`)

Assesses flood risk based on water level sensor data:

**Input:**

- `avg_water_level`: Average water level (cm) over last 10 minutes
- `max_water_level`: Peak water level in that period
- `trend`: Rising, falling, or stable

**Thresholds:**

- LOW_THRESHOLD: 50 cm
- MEDIUM_THRESHOLD: 100 cm
- CRITICAL_THRESHOLD: 150 cm

**Rules:**

1. If avg < 50cm → LOW risk
2. If 50cm ≤ avg ≤ 100cm → MEDIUM risk
3. If avg > 100cm → HIGH risk
4. If trend is rising → increase risk by 15%
5. If trend is falling → decrease risk by 15%
6. If recent spike (max > 150cm) → increase risk by 10%

**Output:** Risk level (LOW/MEDIUM/HIGH) with confidence score 0-1

### AHP Module (`ahp_service.py`)

Calculates household vulnerability using weighted scoring:

**Vulnerability Factors:**

- Elderly (age ≥ 60): Weight 35%
- Infants (age ≤ 2): Weight 40%
- Pregnant residents: Weight 15%
- PWD (Persons with Disabilities): Weight 10%

**Scoring:**

- Each factor contributes based on count and household composition
- Infants: 3x weight (highest vulnerability)
- Elderly: 2.5x weight
- Pregnant: 1.5x weight
- PWD: 1.2x weight

**Output:** Priority score 0-1 (0 = low, 1 = critical vulnerability)

### Decision Engine (`decision_service.py`)

Combines risk + priority into action recommendation:

| Risk Level | Priority      | Recommendation       |
| ---------- | ------------- | -------------------- |
| HIGH       | HIGH/CRITICAL | **IMMEDIATE RELIEF** |
| HIGH       | MODERATE      | **PREPARE**          |
| HIGH       | LOW           | **PREPARE**          |
| MEDIUM     | HIGH/CRITICAL | **IMMEDIATE RELIEF** |
| MEDIUM     | MODERATE      | **PREPARE**          |
| MEDIUM     | LOW           | **PREPARE**          |
| LOW        | HIGH          | **PREPARE**          |
| LOW        | LOW           | **SAFE**             |

**Human Override:** API supports passing `override_action` to override AI recommendation.

## 🌐 Deployment on Render

### Prerequisites

- GitHub account with repository
- Render account (free tier available at https://render.com)

### Step 1: Prepare GitHub Repository

1. Initialize git repository (if not already done):

   ```bash
   cd "Human in the loop AI"
   git init
   git add .
   git commit -m "Initial commit: AI Decision Service"
   ```

2. Create repository on GitHub and push:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Create Render Service

1. Go to https://render.com and sign in
2. Click **New +** → **Web Service**
3. Select your GitHub repository
4. Configure the service:
   - **Name**: `ai-decision-service`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port 10000`
   - **Instance Type**: Starter (free tier)

### Step 3: Add Environment Variables

In Render dashboard, go to your service and click **Environment**. Add:

```
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/disaster_management?retryWrites=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
ENV=production
PORT=10000
ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com
TRUSTED_HOSTS=yourdomain.com,api.yourdomain.com
```

### Step 4: Deploy

1. Click **Deploy** button
2. Wait for deployment to complete (usually 2-5 minutes)
3. Your service URL will be: `https://ai-decision-service.onrender.com`

### Step 5: Verify Deployment

```bash
curl https://ai-decision-service.onrender.com/health

# Test the decision endpoint
curl -X POST https://ai-decision-service.onrender.com/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'
```

### MongoDB Atlas Network Access

Important: Whitelist Render IP address in MongoDB Atlas:

1. Go to MongoDB Atlas Dashboard
2. Network Access → IP Whitelist
3. Add: `0.0.0.0/0` (or specific Render IP if available)

### Supabase CORS Settings (Optional)

If accessing from frontend, ensure CORS is configured in Supabase:

1. Go to Supabase Dashboard
2. Authentication → URL Configuration
3. Add your domain to Redirect URLs

## 📊 Database Schemas

### MongoDB: sensor_readings

```json
{
  "_id": ObjectId,
  "barangay_id": 1,
  "water_level": 65.5,
  "location": "Bridge near Barangay 1",
  "timestamp": ISODate("2024-05-03T10:30:00Z")
}
```

### Supabase: residents

```sql
id                | INTEGER PRIMARY KEY
barangay_id       | INTEGER NOT NULL
age               | INTEGER
is_pregnant       | BOOLEAN DEFAULT FALSE
is_pwd            | BOOLEAN DEFAULT FALSE
created_at        | TIMESTAMP DEFAULT NOW()
```

## 🔍 Logging and Monitoring

The service logs important events:

```
2024-05-03 10:30:45 - app.services.decision_service - INFO - Making decision for barangay 1
2024-05-03 10:30:46 - app.services.fuzzy_service - INFO - Risk assessment: level=HIGH, confidence=0.95, trend=rising
2024-05-03 10:30:46 - app.services.ahp_service - INFO - AHP Priority Score: 0.820 - Factors: Elderly (2), Infants (1)
2024-05-03 10:30:46 - app.services.decision_service - INFO - Decision made for barangay 1: IMMEDIATE RELIEF (confidence: 0.85)
```

Check logs:

- **Local**: Console output when running with `--reload`
- **Render**: Dashboard → Logs tab

## 🛡️ Security Best Practices

1. **Environment Variables**: Never commit `.env` file
2. **CORS**: Restrict to known origins
3. **Input Validation**: Pydantic validates all inputs
4. **Error Handling**: Errors don't leak sensitive info
5. **HTTPS**: Always use HTTPS in production (Render provides free SSL)
6. **Database**: Use strong passwords and network restrictions

## 🚨 Troubleshooting

### MongoDB Connection Error

```
Error: Failed to connect to MongoDB: connection refused
```

**Solution:** Check MONGODB_URI in .env and whitelist IP in MongoDB Atlas

### Supabase Connection Error

```
Error: Failed to connect to Supabase: [Errno -2] Name or service not known
```

**Solution:** Verify SUPABASE_URL and SUPABASE_KEY

### No Sensor Data Found

```
WARNING - No sensor data found for barangay 1
```

**Solution:** Insert test data into MongoDB `sensor_readings` collection

### Port Already in Use

```
OSError: [Errno 48] Address already in use
```

**Solution:** Change port in command: `--port 10001`

## 📝 License

This project is part of a thesis on Human-in-the-Loop AI for disaster management.

## 👤 Author

Senior Backend Engineer & AI Systems Architect

---

**For production deployment, ensure:**

- ✅ Database backups configured
- ✅ Monitoring and alerting set up
- ✅ Load testing completed
- ✅ Security audit passed
- ✅ Documentation reviewed
