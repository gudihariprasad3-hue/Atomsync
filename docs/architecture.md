# AtmoSync – System Architecture

## Architecture Overview

```
+---------------------------+
|   Python IoT Simulator    |   simulator/sensor_generator.py
|   5 containers × 5 types |   simulator/config.py
+---------------------------+
            |
     JSON sensor events
            |
            v
+---------------------------+
|   Apache Kafka Producer   |   kafka/producer.py
|   Topic: atmosync-sensor  |   kafka/config.py
+---------------------------+
            |
    Kafka topic (Docker)
            |
            v
+---------------------------+
|   Apache Kafka Consumer   |   kafka/consumer.py
|   Group: atmosync-group   |
+---------------------------+
            |
     Validated readings
            |
            v
+---------------------------+
|   Snowflake Data Warehouse|   snowflake/schema.sql
|   ATMOSYNC_DB             |   snowflake/connection.py
|   RAW.RAW_SENSOR_READINGS |   snowflake/load_data.py
+---------------------------+
            |
     Raw IoT data
            |
            v
+---------------------------+
|   dbt Core Transformations|   dbt/models/staging/
|   Staging Layer (views)   |   stg_sensor_readings.sql
|   STAGING schema          |   stg_commodity_prices.sql
+---------------------------+   stg_market_routes.sql
            |
     Cleaned typed data
            |
            v
+---------------------------+
|   dbt Analytics Models    |   dbt/models/marts/
|   Marts Layer (tables)    |   mart_spoilage_analysis.sql
|   MARTS schema            |   mart_arbitrage_opportunities.sql
+---------------------------+   mart_container_health.sql
            |
     Business analytics
            |
            v
+---------------------------+
|   Apache Superset         |   docker-compose.yml
|   Dashboard on :8088      |   dashboard/superset/
|   10 chart panels         |
+---------------------------+
            |
     Spoilage Arbitrage Insights
            |
            v
+---------------------------+
|   Alternative Market      |   analytics/arbitrage_engine.py
|   Recommendation Engine   |   analytics/spoilage_engine.py
+---------------------------+
            |
     RECOMMEND_REROUTE alerts
            |
            v
+---------------------------+
|   Alert Manager           |   alerts/alert_manager.py
|   - Local log file        |
|   - Slack webhook         |
|   - Gmail SMTP            |
+---------------------------+
```

---

## Component Details

### Module A – Python IoT Simulator

**Files**: `simulator/sensor_generator.py`, `simulator/config.py`

**Key Design Decisions**:
- Uses `ContainerState` class to maintain state across readings (realistic drift)
- Anomaly injection controlled by `AnomalyConfig` with per-type probabilities
- `create_sensor_reading()` validates all readings before returning
- Sample dataset generation uses fixed seed (42) for reproducibility

**Sensor Reading Schema**:
```json
{
  "event_id": "uuid4",
  "container_id": "CTR-001",
  "timestamp": "2026-11-24T10:00:00+00:00",
  "temperature_celsius": 5.5,
  "humidity_percent": 90.0,
  "vibration_ms2": 0.3,
  "commodity": "AVOCADO",
  "origin": "Mexico City",
  "destination": "New York",
  "hours_in_transit": 12.0,
  "condition": "NORMAL",
  "anomalies": [],
  "thresholds": {...}
}
```

---

### Module B – Apache Kafka Streaming

**Files**: `kafka/producer.py`, `kafka/consumer.py`, `kafka/config.py`

**Key Design Decisions**:
- Producer uses container_id as partition key → ordered processing per container
- Consumer uses pluggable `MessageHandler` pattern (add handlers without changing core)
- Both have file-mode fallback (test without running Kafka)
- All config from environment variables

**Kafka Topics**:
- `atmosync-sensor-events` – raw IoT sensor readings
- `atmosync-alerts` – processed alerts

---

### Module C – Snowflake Data Warehouse

**Files**: `snowflake/schema.sql`, `snowflake/connection.py`, `snowflake/load_data.py`

**Schema Design**:

| Schema | Purpose | Tables |
|---|---|---|
| RAW | Direct ingest from Kafka | RAW_SENSOR_READINGS |
| PRICING | Reference data | COMMODITY_PRICES, MARKET_ROUTES, CONTAINER_REGISTRY |
| STAGING | Cleaned data (dbt) | stg_* views |
| MARTS | Analytics (dbt) | mart_* tables |

**Key Design Decisions**:
- `RAW_PAYLOAD VARIANT` column stores full original JSON
- Snowflake Stream (CDC) on raw table for incremental dbt loads
- Warehouse auto-suspend after 60 seconds (cost saving)

---

### Module D – dbt Transformation

**Files**: `dbt/models/staging/`, `dbt/models/marts/`

**Transformation Layers**:

```
RAW.RAW_SENSOR_READINGS
        ↓ (view)
STAGING.stg_sensor_readings      ← clean + type-cast + anomaly flags
STAGING.stg_commodity_prices     ← active prices only
STAGING.stg_market_routes        ← routes joined with container registry
        ↓ (table)
MARTS.mart_spoilage_analysis     ← spoilage scores per container
MARTS.mart_arbitrage_opportunities ← rerouting analysis per alternative
MARTS.mart_container_health      ← Superset dashboard source table
```

**Data Quality Tests**:
- Unique: event_id, container_id (registry), route_id
- Not null: all sensor fields, container_id
- Accepted values: commodity types, condition flags, risk levels

---

### Module E – Analytics Engines

**Files**: `analytics/spoilage_engine.py`, `analytics/arbitrage_engine.py`

Both engines are pure Python (no Snowflake required) for:
- Real-time Kafka consumer alerts
- Local testing without cloud access
- Standalone demonstration

---

### Module F – Apache Superset Dashboard

**Deployment**: Docker Compose (`docker-compose.yml`)  
**Access**: http://localhost:8088 (admin / atmosync2024)

**Dashboard Panels**:
1. Container Status Overview (health score cards)
2. Temperature Trends (line chart by container)
3. Humidity Trends (line chart)
4. Vibration Monitor (bar chart)
5. Container Health Indicators (gauge charts)
6. At-Risk Container Table (filterable)
7. Spoilage Risk Analysis (scatter plot: score vs time)
8. Time-to-Spoilage Indicators (countdown numbers)
9. Arbitrage Opportunities (ranked table)
10. Alternative Market Recommendations (map/table)

**Data Source**: `MARTS.mart_container_health` (refreshes every 5 minutes)

---

### Module G – Alerts & Automation

**File**: `alerts/alert_manager.py`

**Alert Channels** (in priority order):
1. **Local log file** `logs/alerts.log` – always active, JSON format
2. **Slack webhook** – set `SLACK_WEBHOOK_URL` in `.env`
3. **Gmail SMTP** – set email vars in `.env`

**Alert Triggers**:
- Spoilage score ≥ 70% (configurable via `ALERT_SPOILAGE_THRESHOLD`)
- Arbitrage margin ≥ $500 with RECOMMEND_REROUTE (configurable)

---

## Security Architecture

| Credential | Storage | Access |
|---|---|---|
| Snowflake password | `.env` file (never committed) | `python-dotenv` |
| Kafka bootstrap | `.env` file | `python-dotenv` |
| Slack webhook | `.env` file | `python-dotenv` |
| Email password | `.env` file | `python-dotenv` |
| Superset secret | docker-compose env | Change in production |

---

## Local Development vs. Cloud Architecture

| Component | Local Development | Production |
|---|---|---|
| Kafka | Docker Compose | Confluent Cloud / MSK |
| Snowflake | Same (cloud-native) | Same |
| dbt | Local CLI | dbt Cloud / Airflow |
| Superset | Docker Compose | Managed / EC2 |
| Alerts | Local log file | Slack + Email |
