# AtmoSync – Micro-Climate Arbitrage Analytics

> **End-to-end data engineering platform for hyper-local IoT container monitoring, spoilage prediction and arbitrage opportunity detection.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://python.org)
[![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-Streaming-orange)](https://kafka.apache.org)
[![Snowflake](https://img.shields.io/badge/Snowflake-Data%20Warehouse-lightblue)](https://snowflake.com)
[![dbt](https://img.shields.io/badge/dbt-Transformation-red)](https://getdbt.com)
[![Apache Superset](https://img.shields.io/badge/Apache%20Superset-BI-green)](https://superset.apache.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🌡️ Problem Statement

Traditional supply chain analytics rely on standard transit times and macro-weather forecasts. They **cannot track hyper-local climate changes** inside individual agricultural shipping containers.

Internal temperature, humidity, and vibration shifts degrade commodities before arrival — causing:
- Undetected spoilage
- Missed rerouting opportunities
- Unnecessary financial losses

---

## 🎯 Solution

AtmoSync ingests **real-time IoT sensor telemetry** from shipping containers, stores it in **Snowflake**, transforms it with **dbt**, and surfaces actionable **Spoilage Arbitrage** insights on an **Apache Superset** dashboard.

When Container A's temperature drifts above threshold, the system:
1. Calculates spoilage degradation rate
2. Estimates time-to-spoilage
3. Compares travel time to original vs. alternative markets
4. Recommends rerouting with estimated arbitrage margin

---

## 🏗️ Architecture

```
Python IoT Simulator
        │
        ▼
Apache Kafka Producer ──► Kafka Topic ──► Kafka Consumer
                                                │
                                                ▼
                                    Snowflake Raw Tables
                                                │
                                                ▼
                                    dbt Staging Models
                                                │
                                                ▼
                                    dbt Analytics Models
                                                │
                                                ▼
                                Apache Superset Dashboard
                                                │
                                                ▼
                                Spoilage Arbitrage Insights
                                                │
                                                ▼
                                Alternative Market Recommendation
```

---

## 📦 Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Simulation | Python 3.9+ | IoT container sensor data generation |
| Streaming | Apache Kafka | Real-time event ingestion |
| Storage | Snowflake | Cloud data warehouse |
| Transformation | dbt Core | SQL models and data quality |
| Analytics | Python | Spoilage & arbitrage calculations |
| Visualization | Apache Superset | Executive BI dashboard |
| Orchestration | Docker Compose | Local service deployment |

---

## 📁 Project Structure

```
AtmoSync/
├── simulator/
│   ├── sensor_generator.py    # IoT sensor simulation engine
│   └── config.py              # Sensor thresholds and container config
├── kafka/
│   ├── producer.py            # Kafka producer – publishes sensor events
│   ├── consumer.py            # Kafka consumer – receives and stores events
│   └── config.py              # Kafka connection configuration
├── snowflake/
│   ├── schema.sql             # Database schema DDL
│   ├── connection.py          # Secure Snowflake connector
│   └── load_data.py           # Data loading utilities
├── dbt/
│   ├── dbt_project.yml        # dbt project configuration
│   └── models/
│       ├── staging/           # Raw data cleaning
│       └── marts/             # Business analytics models
├── analytics/
│   ├── spoilage_engine.py     # Spoilage degradation calculations
│   └── arbitrage_engine.py   # Arbitrage margin calculations
├── dashboard/
│   └── superset/              # Superset configuration and exports
├── data/
│   └── sample_data/           # Repeatable test datasets
├── tests/
│   ├── test_simulator.py
│   ├── test_kafka.py
│   ├── test_snowflake.py
│   ├── test_analytics.py
│   └── test_integration.py
├── docs/
│   ├── architecture.md
│   ├── installation.md
│   └── calculations.md
├── alerts/
│   └── alert_manager.py       # Slack/email/local alert system
├── .env.example               # Environment variable template
├── .gitignore                 # Git ignore rules
├── requirements.txt           # Python dependencies
├── docker-compose.yml         # Kafka + Superset services
└── README.md                  # This file
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Docker Desktop
- Git
- Snowflake account (free trial: [signup](https://signup.snowflake.com))

### 1. Clone and configure

```bash
git clone https://github.com/gudihariprasad3-hue/Atomsync.git
cd Atomsync
cp .env.example .env
# Edit .env with your credentials
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Kafka (Docker)

```bash
docker-compose up -d kafka zookeeper
```

### 4. Run the simulator

```bash
python simulator/sensor_generator.py
```

### 5. Start Kafka consumer

```bash
python kafka/consumer.py
```

### 6. Set up Snowflake schema

```bash
# Run schema.sql in your Snowflake worksheet
# Then test connection:
python snowflake/connection.py
```

### 7. Run dbt models

```bash
cd dbt
dbt run
dbt test
```

### 8. Launch Superset

```bash
docker-compose up -d superset
# Open http://localhost:8088
```

---

## 📊 Key Analytics

### Spoilage Degradation Model

> ⚠️ **Disclaimer**: The following are **mock calculations for demonstration purposes only**. They are NOT scientifically validated spoilage predictions and should not be used for real-world commodity decisions.

The spoilage engine uses these simulated factors:
- **Temperature deviation** from optimal storage range
- **Humidity exceedance** beyond safe thresholds
- **Vibration anomalies** accelerating bruising/damage
- **Cumulative exposure time**

### Arbitrage Margin Calculation

```
Arbitrage Margin = 
    (Alternative Market Price × Quantity × Remaining Quality %)
  - (Original Market Price × Quantity × Degraded Quality %)
  - Rerouting Cost
```

---

## 🔧 Development Phases

| Phase | Module | Status |
|---|---|---|
| Phase 2 | Foundation & Structure | ✅ COMPLETE |
| Phase 3 | IoT Sensor Simulator | 🔄 IN PROGRESS |
| Phase 4 | Kafka Producer/Consumer | ⏳ PENDING |
| Phase 5 | Snowflake Schema & Connection | ⏳ PENDING |
| Phase 6 | dbt Transformation Models | ⏳ PENDING |
| Phase 7 | Spoilage & Arbitrage Analytics | ⏳ PENDING |
| Phase 8 | Apache Superset Dashboard | ⏳ PENDING |
| Phase 9 | Integration & Final Testing | ⏳ PENDING |

---

## 📄 Documentation

- [Architecture Overview](docs/architecture.md)
- [Installation Guide](docs/installation.md)
- [Calculations & Assumptions](docs/calculations.md)

---

## ⚖️ License

MIT License – see [LICENSE](LICENSE) for details.

---

## 👨‍💻 Author

Built as part of the Infotact Data Engineering Programme.
