# SmartFlood V2–V3 Human-in-the-Loop AI Decision Service

## 📖 Overview

The **SmartFlood Human-in-the-Loop AI Decision Service** is the standalone AI backend that powers the decision support system for **SmartFlood V2** and **SmartFlood V3**.

Unlike the SmartFlood web application, this repository focuses exclusively on AI-assisted disaster response by analyzing **real-time flood sensor data** together with **household vulnerability information**.

The service combines **Fuzzy Logic**, **Analytical Hierarchy Process (AHP)**, and **Human-in-the-Loop decision making** to generate transparent and explainable recommendations for flood relief allocation.

This microservice was intentionally developed as an independent backend, allowing the AI engine to evolve separately from the SmartFlood web platform.

---

# 🎯 Project Objectives

The objectives of this project were to:

* Build an explainable AI decision engine for disaster management.
* Analyze real-time flood conditions using IoT sensor data.
* Evaluate household vulnerability using AHP.
* Recommend relief priorities based on flood severity and vulnerable populations.
* Support disaster response personnel through Human-in-the-Loop decision making.
* Provide AI functionality through REST APIs for integration with SmartFlood.

---

# ✨ Features

## 🤖 Explainable AI

Unlike traditional black-box machine learning models, this system generates recommendations using transparent and explainable techniques.

Implemented algorithms include:

* Fuzzy Logic
* Analytical Hierarchy Process (AHP)
* Rule-Based Decision Engine

Every recommendation includes an explanation describing how the final decision was generated.

---

## 👨‍💻 Human-in-the-Loop Decision Support

The AI does **not** make autonomous disaster decisions.

Instead, it assists administrators by providing recommendations that can still be reviewed, validated, or overridden by authorized personnel.

This approach improves transparency while keeping humans responsible for the final decision.

---

## 🌊 Real-Time Sensor Integration

The AI continuously retrieves flood monitoring information from **MongoDB Atlas**, including:

* Water level readings
* Sensor trends
* Historical measurements

These values are analyzed to determine the current flood risk.

---

## 👨‍👩‍👧 Household Vulnerability Assessment

Resident information is retrieved from **Supabase**, including:

* Elderly residents
* Infants
* Pregnant women
* Persons with Disabilities (PWD)

The AHP algorithm evaluates household vulnerability before calculating the overall relief priority.

---

## 🚑 Relief Recommendation Engine

The final recommendation combines:

* Flood Risk (Fuzzy Logic)
* Household Vulnerability (AHP)
* Available Relief Equipment
* Administrative Inputs

The system then recommends the most appropriate disaster response action.

---

# 🛠️ Technologies Used

### Backend

* Python
* FastAPI

### Databases

* MongoDB Atlas
* Supabase

### AI Techniques

* Human-in-the-Loop AI
* Fuzzy Logic
* Analytical Hierarchy Process (AHP)

### Deployment History

Throughout development, the AI service was deployed on multiple cloud platforms to evaluate deployment reliability and free-tier limitations.

* Render (Initial Deployment)
* Railway (Performance Evaluation)
* Heroku (Final Capstone Deployment)

---

# 🏗️ System Architecture

```text
                     IoT Flood Sensors
                            │
                            ▼
                     MongoDB Atlas
                            │
                            ▼
          SmartFlood Human-in-the-Loop AI
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Fuzzy Logic        AHP Engine        Decision Engine
                            │
                            ▼
                  SmartFlood Web Platform
```

---

# 🚧 Engineering Challenges

## Explainable AI

Instead of using a traditional machine learning classifier, the project was intentionally designed around explainable AI techniques so disaster response personnel could understand why every recommendation was generated.

---

## Cloud Deployment Evaluation

Several hosting providers were evaluated throughout development.

The AI backend was deployed on:

* Render
* Railway
* Heroku

This allowed comparison of deployment speed, cold-start behavior, reliability, and suitability for hosting FastAPI-based AI services.

---

## Multi-Database Integration

The AI service communicates with multiple cloud databases.

**MongoDB Atlas**

* Real-time IoT sensor data
* Flood monitoring information

**Supabase**

* Household information
* Vulnerability assessment data
* AHP-related records

Combining these independent datasets required designing an API capable of coordinating multiple external services into a unified decision engine.

---

# 📚 Lessons Learned

Developing this project helped me understand:

* FastAPI backend development
* Microservice architecture
* REST API design
* Cloud deployment
* Explainable AI
* Human-in-the-Loop systems
* Fuzzy Logic
* Analytical Hierarchy Process (AHP)
* Multi-database integration
* Production-oriented API development

One of the most valuable lessons from this project was realizing that AI systems for disaster management should **support** human decision-makers rather than replace them.

By combining explainable algorithms with administrative oversight, the platform provides transparent recommendations while preserving human accountability.

---

# 🔗 Relationship to SmartFlood

This repository serves as the dedicated AI backend for:

* ✅ SmartFlood V2
* ✅ SmartFlood V3

Separating the AI engine into its own microservice allowed the SmartFlood platform to evolve independently while maintaining a reusable decision engine for future versions.

---

# 📌 Current Status

**🚀 Production AI Microservice (Capstone Version)**

This repository represents the standalone AI backend developed for the SmartFlood platform.

It demonstrates the integration of explainable AI techniques, cloud databases, and REST APIs to support intelligent disaster management and relief allocation.
