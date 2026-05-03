# Quick Reference Guide

Fast lookup guide for common commands and endpoints.

## 🚀 Quick Start (3 minutes)

```bash
# 1. Setup environment
cd "Human in the loop AI"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your MongoDB URI and Supabase credentials

# 3. Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 10000

# 4. Test
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'
```

---

## 📡 API Endpoints

### Health Check

```
GET /health
Response: {"status": "healthy", "message": "..."}
```

### Get Decision

```
POST /api/v1/decision
Request: {"barangay_id": 1}
Response: {
  "risk_level": "HIGH",
  "priority_score": 0.82,
  "recommended_action": "IMMEDIATE RELIEF",
  "confidence_score": 0.85,
  "explanation": "...",
  "fuzzy_explanation": "...",
  "ahp_explanation": "..."
}
```

### Swagger Documentation

```
GET /docs          # Interactive API docs
GET /redoc         # Alternative documentation
```

---

## 📁 Project Structure

```
app/
├── main.py                 # FastAPI app
├── models/schemas.py       # Pydantic models
├── routes/decision.py      # API endpoints
├── services/
│   ├── fuzzy_service.py    # Risk assessment
│   ├── ahp_service.py      # Vulnerability scoring
│   └── decision_service.py # Combined decision
└── database/
    ├── mongodb.py          # Sensor data
    └── supabase.py         # Household data
```

---

## 🔧 Useful Commands

```bash
# Activate virtual environment
source venv/bin/activate           # macOS/Linux
venv\Scripts\activate.bat          # Windows

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 10000

# Run on different port
uvicorn app.main:app --port 10001

# Run without reload (production)
uvicorn app.main:app --host 0.0.0.0 --port 10000

# Test health
curl http://localhost:10000/health

# Test decision
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'

# View logs in real-time
tail -f app/logs.txt

# Kill process on port 10000
lsof -ti:10000 | xargs kill -9    # macOS/Linux
netstat -ano | findstr :10000     # Windows
```

---

## 🗄️ Database Setup

### MongoDB

```bash
# Insert sample data
db.sensor_readings.insertMany([
  {
    "barangay_id": 1,
    "water_level": 45.0,
    "timestamp": new Date()
  },
  {
    "barangay_id": 1,
    "water_level": 65.0,
    "timestamp": new Date(Date.now() + 300000)
  }
])
```

### Supabase

```sql
-- Create table
CREATE TABLE residents (
  id SERIAL PRIMARY KEY,
  barangay_id INTEGER NOT NULL,
  age INTEGER NOT NULL,
  is_pregnant BOOLEAN DEFAULT FALSE,
  is_pwd BOOLEAN DEFAULT FALSE
);

-- Insert sample data
INSERT INTO residents VALUES
(NULL, 1, 65, FALSE, FALSE),
(NULL, 1, 1, FALSE, FALSE),
(NULL, 1, 28, TRUE, FALSE);
```

---

## 🔑 Environment Variables

```env
# .env file
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/disaster_management?retryWrites=true
SUPABASE_URL=https://project-id.supabase.co
SUPABASE_KEY=your-anon-key
PORT=10000
HOST=0.0.0.0
ENV=development
```

---

## 🧪 Testing

```bash
# Test with curl
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'

# Test with Python
python3 << 'EOF'
import requests
r = requests.post(
    "http://localhost:10000/api/v1/decision",
    json={"barangay_id": 1}
)
print(r.json())
EOF

# Load test (10 requests)
for i in {1..10}; do
  curl -X POST http://localhost:10000/api/v1/decision \
    -H "Content-Type: application/json" \
    -d '{"barangay_id": 1}' &
done
wait
```

---

## 🚀 Deployment to Render

```bash
# 1. Initialize git
git init
git add .
git commit -m "Initial commit"

# 2. Push to GitHub
git remote add origin https://github.com/user/repo.git
git push -u origin main

# 3. Create on Render.com
# - New Web Service
# - Connect GitHub repository
# - Build: pip install -r requirements.txt
# - Start: uvicorn app.main:app --host 0.0.0.0 --port 10000
# - Add environment variables
# - Deploy

# 4. Test deployment
curl https://service-name.onrender.com/health
```

---

## 📊 Algorithm Summary

### Fuzzy Logic (Risk Assessment)

- **Input**: avg_water_level, max_water_level, trend
- **Thresholds**: 50cm (LOW), 100cm (MEDIUM), 150cm (HIGH)
- **Output**: Risk level + confidence (0-1)

### AHP (Vulnerability Scoring)

- **Input**: elderly, infants, pregnant, pwd counts
- **Weights**: Infants 40%, Elderly 35%, Pregnant 15%, PWD 10%
- **Output**: Priority score (0-1)

### Decision Engine

```
IF risk_level = HIGH AND priority >= 0.65
  → IMMEDIATE RELIEF
ELSE IF risk_level = HIGH OR priority >= 0.35
  → PREPARE
ELSE
  → SAFE
```

---

## 🐛 Common Issues

| Issue                 | Solution                                   |
| --------------------- | ------------------------------------------ |
| `ModuleNotFoundError` | `pip install -r requirements.txt`          |
| `Connection refused`  | Check MONGODB_URI and SUPABASE_KEY in .env |
| `Port already in use` | Use different port: `--port 10001`         |
| `Render cold start`   | Upgrade to paid tier for always-on         |
| `No sensor data`      | Insert test data into MongoDB              |

---

## 📚 Documentation Files

| File                 | Purpose              |
| -------------------- | -------------------- |
| `README.md`          | Complete overview    |
| `SETUP.md`           | Detailed setup steps |
| `EXAMPLES.md`        | API examples         |
| `PROJECT_SUMMARY.md` | Full project summary |
| `QUICK_REFERENCE.md` | This file            |

---

## 🎯 Key Files to Understand

1. **app/main.py** - Start here to understand app structure
2. **app/models/schemas.py** - See data models
3. **app/services/fuzzy_service.py** - Understand risk logic
4. **app/services/ahp_service.py** - Understand priority scoring
5. **app/services/decision_service.py** - See combined decision logic
6. **app/routes/decision.py** - See API endpoints

---

## 💡 Tips

- Use `--reload` for development (auto-restart on changes)
- Check logs at `http://localhost:10000/docs` for details
- Swagger UI at `/docs` is great for testing
- Always use `.env` for secrets, never commit it
- Render free tier sleeps after 15 min inactivity
- MongoDB/Supabase free tier is sufficient for testing

---

## 🔗 Quick Links

- **Local API**: http://localhost:10000
- **Swagger Docs**: http://localhost:10000/docs
- **ReDoc**: http://localhost:10000/redoc
- **MongoDB**: https://atlas.mongodb.com
- **Supabase**: https://supabase.com
- **Render**: https://render.com
- **GitHub**: https://github.com

---

## 📝 Running Tests

```bash
# Test health endpoint
curl http://localhost:10000/health

# Test decision endpoint
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'

# Test with Postman
# 1. Import URL: http://localhost:10000/openapi.json
# 2. Create request
# 3. Send

# Test with Python requests
python3 -c "
import requests
r = requests.post('http://localhost:10000/api/v1/decision', json={'barangay_id': 1})
print(r.status_code)
print(r.json())
"
```

---

## 🎓 For Thesis Defense

Key talking points:

- ✅ Explainable AI (rule-based, not ML)
- ✅ Fuzzy logic for complex water level assessment
- ✅ AHP for multi-factor vulnerability
- ✅ Human-in-the-loop override capability
- ✅ Production-ready code quality
- ✅ Real-world data integration
- ✅ Deployed to cloud (Render)

---

**Last Updated**: May 2024
**Version**: 1.0.0
**Status**: Production Ready ✅
