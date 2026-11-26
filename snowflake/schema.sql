"""
============================================================
AtmoSync – Snowflake Database Schema (Module C)
============================================================

HOW TO USE:
  1. Log into your Snowflake account
  2. Open a new Worksheet
  3. Copy and paste this entire file
  4. Click "Run All" or execute section by section

WHAT THIS CREATES:
  - Database: ATMOSYNC_DB
  - Schemas:  RAW, STAGING, MARTS, PRICING
  - Tables:   Raw sensor data, commodity pricing,
              market routes, container registry
============================================================
*/

-- ============================================================
-- STEP 1: CREATE DATABASE AND WAREHOUSE
-- ============================================================

-- Create the AtmoSync database (if it doesn't exist)
CREATE DATABASE IF NOT EXISTS ATMOSYNC_DB
    DATA_RETENTION_TIME_IN_DAYS = 7
    COMMENT = 'AtmoSync Micro-Climate Arbitrage Analytics';

-- Create compute warehouse
CREATE WAREHOUSE IF NOT EXISTS ATMOSYNC_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60          -- Suspend after 60 seconds of inactivity (saves cost)
    AUTO_RESUME = TRUE
    COMMENT = 'AtmoSync compute warehouse';

-- Use the database and warehouse
USE DATABASE ATMOSYNC_DB;
USE WAREHOUSE ATMOSYNC_WH;

-- ============================================================
-- STEP 2: CREATE SCHEMAS
-- ============================================================
-- RAW     = unprocessed data from Kafka/IoT
-- STAGING = cleaned and typed data (dbt staging models)
-- MARTS   = business analytics (dbt mart models)
-- PRICING = commodity price reference data

CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'Raw IoT sensor readings from Kafka consumer';

CREATE SCHEMA IF NOT EXISTS STAGING
    COMMENT = 'Cleaned and typed sensor data (dbt staging layer)';

CREATE SCHEMA IF NOT EXISTS MARTS
    COMMENT = 'Business analytics and arbitrage models (dbt marts)';

CREATE SCHEMA IF NOT EXISTS PRICING
    COMMENT = 'Mock commodity pricing and market route data';

-- ============================================================
-- STEP 3: RAW SCHEMA TABLES
-- ============================================================

USE SCHEMA RAW;

-- Raw IoT sensor readings (landed directly from Kafka consumer)
CREATE TABLE IF NOT EXISTS RAW_SENSOR_READINGS (
    -- Auto-generated row identifier
    ROW_ID              NUMBER AUTOINCREMENT PRIMARY KEY,

    -- Event identification
    EVENT_ID            VARCHAR(36)     NOT NULL,       -- UUID from simulator
    CONTAINER_ID        VARCHAR(20)     NOT NULL,       -- e.g. CTR-001

    -- Timestamps
    EVENT_TIMESTAMP     TIMESTAMP_TZ    NOT NULL,       -- Sensor reading time (UTC)
    LOADED_TIMESTAMP    TIMESTAMP_TZ    DEFAULT CURRENT_TIMESTAMP(),  -- When loaded

    -- Sensor readings
    TEMPERATURE_CELSIUS FLOAT           NOT NULL,
    HUMIDITY_PERCENT    FLOAT           NOT NULL,
    VIBRATION_MS2       FLOAT           NOT NULL,

    -- Container context
    COMMODITY           VARCHAR(50)     NOT NULL,       -- e.g. AVOCADO
    ORIGIN              VARCHAR(100),
    DESTINATION         VARCHAR(100),
    HOURS_IN_TRANSIT    FLOAT,

    -- Condition flags
    CONDITION           VARCHAR(20),                    -- NORMAL, WARNING, CRITICAL
    ANOMALIES           VARIANT,                        -- JSON array of anomaly types

    -- Raw JSON payload (keep the full original message)
    RAW_PAYLOAD         VARIANT,

    -- Thresholds snapshot
    THRESHOLDS          VARIANT                         -- JSON object of thresholds at time of reading
)
COMMENT = 'Raw IoT sensor readings ingested from Kafka topic atmosync-sensor-events';

-- Create a stream for change data capture (useful for incremental dbt loads)
CREATE STREAM IF NOT EXISTS RAW_SENSOR_STREAM
    ON TABLE RAW_SENSOR_READINGS
    COMMENT = 'CDC stream for new sensor readings';

-- ============================================================
-- STEP 4: PRICING SCHEMA TABLES
-- ============================================================

USE SCHEMA PRICING;

-- Mock commodity prices at different markets
-- DISCLAIMER: These are illustrative mock prices for demonstration only.
-- They do NOT represent real market prices.
CREATE TABLE IF NOT EXISTS COMMODITY_PRICES (
    PRICE_ID            NUMBER AUTOINCREMENT PRIMARY KEY,
    COMMODITY           VARCHAR(50)     NOT NULL,
    MARKET_NAME         VARCHAR(100)    NOT NULL,
    CITY                VARCHAR(100)    NOT NULL,
    PRICE_PER_UNIT_USD  FLOAT           NOT NULL,       -- USD per kg
    EFFECTIVE_DATE      DATE            NOT NULL,
    EXPIRY_DATE         DATE,
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,
    NOTES               VARCHAR(500)
)
COMMENT = 'Mock commodity prices by market. NOT real market data.';

-- Mock market route information
CREATE TABLE IF NOT EXISTS MARKET_ROUTES (
    ROUTE_ID            NUMBER AUTOINCREMENT PRIMARY KEY,
    CONTAINER_ID        VARCHAR(20)     NOT NULL,
    ORIGIN_CITY         VARCHAR(100)    NOT NULL,
    DESTINATION_CITY    VARCHAR(100)    NOT NULL,
    MARKET_NAME         VARCHAR(100)    NOT NULL,
    IS_ORIGINAL_DEST    BOOLEAN         DEFAULT FALSE,
    HOURS_FROM_CURRENT  FLOAT           NOT NULL,       -- Estimated travel time
    DISTANCE_KM         FLOAT,                          -- Optional
    TRANSPORT_MODE      VARCHAR(50)     DEFAULT 'truck',
    REROUTING_COST_USD  FLOAT           DEFAULT 0.0
)
COMMENT = 'Mock shipping routes and alternative market destinations';

-- Container registry with commodity assignments
CREATE TABLE IF NOT EXISTS CONTAINER_REGISTRY (
    CONTAINER_ID            VARCHAR(20) PRIMARY KEY,
    COMMODITY               VARCHAR(50) NOT NULL,
    COMMODITY_QUANTITY_KG   FLOAT       NOT NULL,
    ORIGIN                  VARCHAR(100),
    ORIGINAL_DESTINATION    VARCHAR(100),
    OPTIMAL_TEMP_MIN        FLOAT,
    OPTIMAL_TEMP_MAX        FLOAT,
    SHELF_LIFE_DAYS         FLOAT,
    LOAD_DATE               DATE,
    NOTES                   VARCHAR(500)
)
COMMENT = 'Registry of active shipping containers and their contents';

-- ============================================================
-- STEP 5: STAGING AND MART TABLES (Managed by dbt)
-- ============================================================
-- Note: Tables in STAGING and MARTS are created and managed
-- by dbt models. We create the schemas here but dbt will
-- create the actual tables when you run: dbt run

-- ============================================================
-- STEP 6: SEED DATA – Container Registry
-- ============================================================

USE SCHEMA PRICING;

INSERT INTO CONTAINER_REGISTRY VALUES
('CTR-001', 'AVOCADO',    18000, 'Mexico City',  'New York',  4.0,  7.0,  21.0, '2026-11-01', 'Primary avocado shipment'),
('CTR-002', 'STRAWBERRY', 12000, 'California',   'Chicago',   0.0,  4.0,   7.0, '2026-11-20', 'Seasonal strawberry batch'),
('CTR-003', 'BANANA',     20000, 'Ecuador',      'Miami',    13.0, 15.0,  14.0, '2026-11-10', 'Standard banana cargo'),
('CTR-004', 'MANGO',      15000, 'Brazil',       'London',   10.0, 13.0,  18.0, '2026-11-05', 'Export premium mangos'),
('CTR-005', 'TOMATO',     16000, 'Florida',      'Boston',   10.0, 12.0,  10.0, '2026-11-22', 'Vine-ripened tomatoes');

-- ============================================================
-- STEP 7: SEED DATA – Mock Commodity Prices
-- DISCLAIMER: All prices below are mock data for demonstration.
-- ============================================================

INSERT INTO COMMODITY_PRICES (COMMODITY, MARKET_NAME, CITY, PRICE_PER_UNIT_USD, EFFECTIVE_DATE, NOTES) VALUES
-- Avocado prices
('AVOCADO', 'New York Market',     'New York',     2.50, '2026-11-01', 'Mock price - demonstration only'),
('AVOCADO', 'Philadelphia Hub',    'Philadelphia', 2.38, '2026-11-01', 'Mock price - demonstration only'),
('AVOCADO', 'Atlanta Market',      'Atlanta',      2.45, '2026-11-01', 'Mock price - demonstration only'),
('AVOCADO', 'Baltimore Fresh',     'Baltimore',    2.30, '2026-11-01', 'Mock price - demonstration only'),

-- Strawberry prices
('STRAWBERRY', 'Chicago Fresh',    'Chicago',      4.80, '2026-11-01', 'Mock price - demonstration only'),
('STRAWBERRY', 'Detroit Wholesale','Detroit',      4.66, '2026-11-01', 'Mock price - demonstration only'),
('STRAWBERRY', 'Indianapolis Hub', 'Indianapolis', 4.32, '2026-11-01', 'Mock price - demonstration only'),
('STRAWBERRY', 'Milwaukee Fresh',  'Milwaukee',    4.46, '2026-11-01', 'Mock price - demonstration only'),

-- Banana prices
('BANANA', 'Miami Distribution',   'Miami',        1.20, '2026-11-01', 'Mock price - demonstration only'),
('BANANA', 'Tampa Fresh',          'Tampa',        1.22, '2026-11-01', 'Mock price - demonstration only'),
('BANANA', 'Atlanta Export',       'Atlanta',      1.18, '2026-11-01', 'Mock price - demonstration only'),
('BANANA', 'Jacksonville Hub',     'Jacksonville', 1.14, '2026-11-01', 'Mock price - demonstration only'),

-- Mango prices
('MANGO', 'London Wholesale',      'London',       3.20, '2026-11-01', 'Mock price - demonstration only'),
('MANGO', 'Amsterdam Fresh',       'Amsterdam',    3.36, '2026-11-01', 'Mock price - demonstration only'),
('MANGO', 'Rotterdam Port',        'Rotterdam',    3.14, '2026-11-01', 'Mock price - demonstration only'),
('MANGO', 'Paris Market',          'Paris',        3.46, '2026-11-01', 'Mock price - demonstration only'),

-- Tomato prices
('TOMATO', 'Boston Fresh',         'Boston',       1.80, '2026-11-01', 'Mock price - demonstration only'),
('TOMATO', 'Providence Fresh',     'Providence',   1.73, '2026-11-01', 'Mock price - demonstration only'),
('TOMATO', 'Hartford Market',      'Hartford',     1.69, '2026-11-01', 'Mock price - demonstration only'),
('TOMATO', 'New Haven Hub',        'New Haven',    1.66, '2026-11-01', 'Mock price - demonstration only');

-- ============================================================
-- STEP 8: SEED DATA – Market Routes
-- ============================================================

INSERT INTO MARKET_ROUTES (CONTAINER_ID, ORIGIN_CITY, DESTINATION_CITY, MARKET_NAME, IS_ORIGINAL_DEST, HOURS_FROM_CURRENT, REROUTING_COST_USD) VALUES
-- CTR-001 (Avocado, Mexico → New York)
('CTR-001', 'Mexico City', 'New York',     'New York Market',  TRUE,  60.0, 0.0),
('CTR-001', 'Mexico City', 'Philadelphia', 'Philadelphia Hub', FALSE,  4.0, 850.0),
('CTR-001', 'Mexico City', 'Atlanta',      'Atlanta Market',   FALSE,  8.0, 1200.0),
('CTR-001', 'Mexico City', 'Baltimore',    'Baltimore Fresh',  FALSE,  5.5, 950.0),

-- CTR-002 (Strawberry, California → Chicago)
('CTR-002', 'California', 'Chicago',       'Chicago Fresh',    TRUE,  40.0, 0.0),
('CTR-002', 'California', 'Detroit',       'Detroit Wholesale',FALSE,  3.5, 600.0),
('CTR-002', 'California', 'Indianapolis',  'Indianapolis Hub', FALSE,  2.0, 400.0),
('CTR-002', 'California', 'Milwaukee',     'Milwaukee Fresh',  FALSE,  2.5, 480.0),

-- CTR-003 (Banana, Ecuador → Miami)
('CTR-003', 'Ecuador', 'Miami',            'Miami Distribution',TRUE, 84.0, 0.0),
('CTR-003', 'Ecuador', 'Tampa',            'Tampa Fresh',      FALSE,  3.0, 350.0),
('CTR-003', 'Ecuador', 'Atlanta',          'Atlanta Export',   FALSE,  7.0, 750.0),
('CTR-003', 'Ecuador', 'Jacksonville',     'Jacksonville Hub', FALSE,  2.0, 280.0),

-- CTR-004 (Mango, Brazil → London)
('CTR-004', 'Brazil', 'London',            'London Wholesale', TRUE, 120.0, 0.0),
('CTR-004', 'Brazil', 'Amsterdam',         'Amsterdam Fresh',  FALSE, 12.0, 2200.0),
('CTR-004', 'Brazil', 'Rotterdam',         'Rotterdam Port',   FALSE, 10.0, 1800.0),
('CTR-004', 'Brazil', 'Paris',             'Paris Market',     FALSE, 14.0, 2500.0),

-- CTR-005 (Tomato, Florida → Boston)
('CTR-005', 'Florida', 'Boston',           'Boston Fresh',     TRUE,  31.0, 0.0),
('CTR-005', 'Florida', 'Providence',       'Providence Fresh', FALSE,  1.5, 150.0),
('CTR-005', 'Florida', 'Hartford',         'Hartford Market',  FALSE,  2.0, 180.0),
('CTR-005', 'Florida', 'New Haven',        'New Haven Hub',    FALSE,  1.8, 165.0);

-- ============================================================
-- STEP 9: VERIFY SETUP
-- ============================================================

SHOW TABLES IN SCHEMA RAW;
SHOW TABLES IN SCHEMA PRICING;
SELECT COUNT(*) AS container_count FROM CONTAINER_REGISTRY;
SELECT COUNT(*) AS price_records   FROM COMMODITY_PRICES;
SELECT COUNT(*) AS route_records   FROM MARKET_ROUTES;
