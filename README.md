## 🏗️ BuildFlow — Construction Management System

## 👋 Personal Introduction

This is my first professional-focused project, created to apply real-world backend concepts, database integration, and external API connections.

BuildFlow was born from a personal inspiration.
My paternal grandfather was a civil engineer, and when I was a child, he used to take me to visit some of the construction sites he worked on.
I enjoyed spending time with his team, and they would show me a bit of their work.
I always found it fascinating how important planning and harmony in execution were — and my grandfather always said that planning is the essence of a good construction project, where every small detail makes a big difference in the final result.

That memory inspired me to create a system that could help other professionals in the construction industry — people like my grandfather — to achieve more efficient planning, a more organized view of progress, and smarter management of weather-related risks that may affect their projects.

---

## 🚀 Project Objective

**BuildFlow** is a **construction management** and monitoring system, developed with **Python + FastAPI** and **PostgreSQL**, designed to provide a solid foundation for:

 - 📋 Registering **projects**, **lots**, and **sectors** of the construction site;
 - 🧱 Recording **daily progress** of activities;
 - 🌦️ Integrating **weather forecasts** via the **Open-Meteo API**;
 - 🚨 Generating **automatic climate risk alerts**;
 - 🪪 Logging **issues (problems and occurrences)** with full history and status tracking.

---

## 🧠 Educational Concept

The project was developed as a **bridge between theory and practice**, with the purpose of consolidating knowledge in:

 - Object-Oriented Programming (OOP) in Python;
 - Database modeling and integration with PostgreSQL;
 - Asynchronous ORM with SQLAlchemy 2.0 + asyncpg;
 - Building RESTful APIs with FastAPI;
 - Backend project architecture best practices;
 - Integration with external/public APIs;
 - Handling meteorological data and automating alerts.

---

## ⚙️ Core Technologies

| Layer         | Technology             |
| ------------- | ---------------------- |
| Language      | Python 3.11            |
| Web Framework | FastAPI                |
| Database      | PostgreSQL             |
| ORM           | SQLAlchemy 2.0 (async) |
| External API  | Open-Meteo             |
| Tools         | PyCharm, PgAdmin       |
| Dependencies  | `requirements.txt`     |
| Tests & Docs  | Swagger UI, HTTPie     |

---

## 🧩 Project Structure
```bash
    buildflow/
    ├─ app/
    │  ├─ __init__.py
    │  ├─ main.py
    │  ├─ api/
    │  │  └─ v1/
    │  │     ├─ router.py
    │  │     ├─ projects.py
    │  │     ├─ lots.py
    │  │     ├─ issues.py
    │  │     ├─ progress.py
    │  │     └─ weather.py
    │  ├─ clients/
    │  │  └─ open_meteo.py
    │  ├─ core/
    │  │  └─ config.py
    │  ├─ db/
    │  │  └─ session.py
    │  ├─ services/
    │  │  ├─ rules_engine.py
    │  │  ├─ apply_rules.py
    │  │  ├─ weather_capture.py
    │  │  └─ weather_normalize.py
    │  └─ utils/
    │     ├─ open_meteo.py
    │     ├─ open_meteo_week.py
    │     └─ weather_codes.py
    ├─ uploads/
    ├─ .env.example
    ├─ requirements.txt
    └─ README.md
```

---

## 💻 How to Run Locally

1️⃣ Clone the repository
    git clone https://github.com/atpyprog/buildflow-backend
    cd buildflow

2️⃣ Create and activate a virtual environment

    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate

3️⃣ Install dependencies

    pip install -r requirements.txt

4️⃣ Configure environment variables

    Copy the .env.example file and rename it to .env.
    Fill it with the correct PostgreSQL credentials and Open-Meteo API configuration:
    
    DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/buildflow
    OPEN_METEO_API_URL=https://api.open-meteo.com/v1/forecast

5️⃣ Run the FastAPI server

    uvicorn app.main:app --reload

    Access the interactive documentation:
    
    Swagger UI → http://127.0.0.1:8000/docs
    
    Redoc → http://127.0.0.1:8000/redoc

---

## 🧭 Project Organization by Features

**BuildFlow** follows a feature-based organization instead of the traditional models/ and schemas/ folders, keeping components close to their domain logic.
```
 Directory	        Function
 - app/api/	        → Defines REST endpoints (FastAPI) divided by functional area (projects, issues, weather, etc.)
 - app/clients/	        → External integrations — such as the Open-Meteo API client
 - app/core/	        → Core configuration and environment variables
 - app/db/	        → Database engine and session management
 - app/services/	→ Domain logic: data capture, normalization, climate risk rules, etc.
 - app/utils/	        → Helper functions and reusable constants (e.g., weather codes, formatting)
```
---

## 🌦️ Open-Meteo Integration

The meteorological module allows querying and storing hourly and daily forecasts for:
```
🌡️ Temperature

🌧️ Rain probability

💨 Wind speed
```
These data are processed and stored in the weather_batch and weather_snapshot tables, serving as the basis for generating preventive issues — alerts indicating adverse conditions (rain, strong winds, etc.) that may affect planned construction activities.

---

## 🧪 Next Steps

 - 🔗 Integration with the Open-Meteo API ✅
 - 📥 Normalization and persistence of weather data ✅
 - 🌩️ Creation of climate risk rules
 - 📊 Implementation of weekly progress reports
 - 🖼️ Real image uploads and field annotations
 - 🌐 Simple web interface for data visualization

 ---

## 💡 On the Use of Artificial Intelligence

BuildFlow also represents a reflection on how technology can work hand in hand with human creativity and reasoning.
During development, AI tools were used as support for idea validation, documentation, and best coding practices.
All technical decisions and implementations were made through human understanding and analysis, with AI used solely as an educational and enhancement tool.

---

## ✍️ Author

Alexandre Tavares

📍 Porto, Portugal

💻 Python Developer in Training

📚 Continuously learning about backend, databases, and API integration
```
“Learning is building. And BuildFlow is part of that construction.”
```

### 🪪 License
This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.
Unauthorized commercial use is prohibited.