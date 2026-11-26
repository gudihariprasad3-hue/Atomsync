# AtmoSync – Installation Guide

## Prerequisites

| Requirement | Minimum Version | Check Command |
|---|---|---|
| Python | 3.9+ | `python --version` |
| Git | Any | via GitHub Desktop |
| Docker Desktop | 4.0+ | `docker --version` |
| Snowflake Account | Free trial OK | [signup](https://signup.snowflake.com) |

---

## Step 1 – Clone the Repository

```bash
git clone https://github.com/gudihariprasad3-hue/Atomsync.git
cd Atomsync
```

---

## Step 2 – Set Up Environment Variables

```bash
# Copy the template
copy .env.example .env

# Open and fill in your values
notepad .env
```

**Required variables:**
```
SNOWFLAKE_ACCOUNT=your_account_identifier
SNOWFLAKE_USER=your_username
SNOWFLAKE_PASSWORD=your_password
```

> ⚠️ Never commit your `.env` file. It is listed in `.gitignore`.

---

## Step 3 – Install Python Dependencies

```bash
pip install -r requirements.txt
```

> On Windows, if `pip` is not found, use `python -m pip install -r requirements.txt`

---

## Step 4 – Start Kafka (Docker)

> Requires Docker Desktop to be running.

```bash
# Start Kafka and Zookeeper
docker-compose up -d zookeeper kafka

# Verify Kafka is running
docker-compose ps

# View Kafka logs
docker-compose logs -f kafka
```

---

## Step 5 – Set Up Snowflake

1. Log into your Snowflake account at https://app.snowflake.com
2. Open a new **Worksheet**
3. Copy and paste the contents of `snowflake/schema.sql`
4. Click **Run All**
5. Test the connection:

```bash
python snowflake/connection.py
```

---

## Step 6 – Run the IoT Simulator

```bash
# Generate sample data (no Kafka required)
python simulator/sensor_generator.py --mode sample

# Run live simulator (console + file output, no Kafka)
python simulator/sensor_generator.py --no-kafka

# Run live simulator with Kafka (requires Step 4)
python simulator/sensor_generator.py
```

---

## Step 7 – Start the Kafka Consumer

```bash
# File mode (test without Kafka)
python kafka/consumer.py --test

# Live Kafka mode
python kafka/consumer.py
```

---

## Step 8 – Run dbt Models

```bash
cd dbt

# Install dbt dependencies
pip install dbt-snowflake

# Copy profiles to dbt home
mkdir %USERPROFILE%\.dbt
copy profiles.yml %USERPROFILE%\.dbt\profiles.yml

# Test connection
dbt debug

# Run all models
dbt run

# Run data quality tests
dbt test
```

---

## Step 9 – Run Analytics Demos

```bash
# Spoilage calculation demo
set PYTHONUTF8=1
python analytics/spoilage_engine.py

# Arbitrage recommendation demo
python analytics/arbitrage_engine.py

# Alert manager test
python alerts/alert_manager.py
```

---

## Step 10 – Launch Apache Superset

```bash
# Start Superset
docker-compose up -d superset

# Open in browser
start http://localhost:8088

# Default credentials
# Username: admin
# Password: atmosync2024
```

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Individual module tests
python -m pytest tests/test_simulator.py -v
python -m pytest tests/test_analytics.py -v
python -m pytest tests/test_kafka.py -v
```

---

## Troubleshooting

### Git not found
Git is bundled with GitHub Desktop at:
`C:\Users\HP\AppData\Local\GitHubDesktop\app-3.7.0\resources\app\git\cmd\git.exe`

### Unicode/encoding errors on Windows
Set the environment variable before running Python:
```
set PYTHONUTF8=1
python your_script.py
```

### Kafka not connecting
Ensure Docker Desktop is running, then:
```bash
docker-compose up -d zookeeper kafka
docker-compose ps
```

### Snowflake connection failed
1. Verify your account identifier format: `orgname-accountname` (e.g., `xy12345.us-east-1`)
2. Ensure your `.env` file exists and has correct values
3. Check that your Snowflake user has SYSADMIN role
