{{
    config(
        materialized='view',
        schema='STAGING',
        tags=['staging', 'sensors'],
        description='Cleaned and typed sensor readings from raw IoT data'
    )
}}

/*
============================================================
stg_sensor_readings.sql – Staging Model
============================================================
PURPOSE:
    Clean and type-cast the raw sensor readings from the
    Kafka consumer. This is the first transformation step.

WHAT IT DOES:
    1. Renames columns to snake_case
    2. Casts timestamps properly
    3. Filters out obviously invalid readings
    4. Adds derived flag columns for downstream use
============================================================
*/

WITH raw_readings AS (

    SELECT
        ROW_ID,
        EVENT_ID,
        CONTAINER_ID,
        EVENT_TIMESTAMP::TIMESTAMP_TZ       AS event_ts,
        LOADED_TIMESTAMP::TIMESTAMP_TZ      AS loaded_ts,
        TEMPERATURE_CELSIUS::FLOAT          AS temperature_c,
        HUMIDITY_PERCENT::FLOAT             AS humidity_pct,
        VIBRATION_MS2::FLOAT                AS vibration_ms2,
        COMMODITY,
        ORIGIN,
        DESTINATION,
        HOURS_IN_TRANSIT::FLOAT             AS hours_in_transit,
        UPPER(TRIM(CONDITION))              AS condition_flag,
        ANOMALIES,
        THRESHOLDS

    FROM {{ source('raw', 'raw_sensor_readings') }}

    -- Exclude test container rows inserted by test scripts
    WHERE CONTAINER_ID NOT LIKE 'CTR-TEST%'

),

-- Data quality filtering: exclude physically impossible readings
valid_readings AS (

    SELECT *
    FROM raw_readings
    WHERE
        temperature_c BETWEEN -30.0 AND 60.0        -- Physical sensor limit
        AND humidity_pct BETWEEN 0.0 AND 100.0
        AND vibration_ms2 >= 0.0
        AND vibration_ms2 <= 20.0
        AND EVENT_ID IS NOT NULL
        AND CONTAINER_ID IS NOT NULL

),

-- Add derived columns used in downstream models
enriched AS (

    SELECT
        ROW_ID                              AS sensor_row_id,
        EVENT_ID                            AS event_id,
        CONTAINER_ID                        AS container_id,
        event_ts,
        loaded_ts,

        -- Sensor values
        temperature_c,
        humidity_pct,
        vibration_ms2,

        -- Context
        COMMODITY                           AS commodity,
        ORIGIN                              AS origin_location,
        DESTINATION                         AS destination_location,
        hours_in_transit,

        -- Condition
        condition_flag,

        -- Anomaly flags (parsed from JSON array)
        IFF(ARRAY_CONTAINS('TEMPERATURE_DRIFT'::VARIANT, ANOMALIES), TRUE, FALSE)
            AS has_temp_drift,
        IFF(ARRAY_CONTAINS('HUMIDITY_ANOMALY'::VARIANT, ANOMALIES), TRUE, FALSE)
            AS has_humidity_anomaly,
        IFF(ARRAY_CONTAINS('VIBRATION_ANOMALY'::VARIANT, ANOMALIES), TRUE, FALSE)
            AS has_vibration_anomaly,

        -- Threshold deviations
        CASE
            WHEN temperature_c > THRESHOLDS:temp_max::FLOAT
                THEN temperature_c - THRESHOLDS:temp_max::FLOAT
            WHEN temperature_c < THRESHOLDS:temp_min::FLOAT
                THEN THRESHOLDS:temp_min::FLOAT - temperature_c
            ELSE 0.0
        END AS temp_deviation_c,

        CASE
            WHEN humidity_pct < THRESHOLDS:humidity_min::FLOAT
                THEN THRESHOLDS:humidity_min::FLOAT - humidity_pct
            WHEN humidity_pct > THRESHOLDS:humidity_max::FLOAT
                THEN humidity_pct - THRESHOLDS:humidity_max::FLOAT
            ELSE 0.0
        END AS humidity_deviation_pct,

        CASE
            WHEN vibration_ms2 > THRESHOLDS:vibration_warning::FLOAT
                THEN vibration_ms2 - THRESHOLDS:vibration_warning::FLOAT
            ELSE 0.0
        END AS vibration_excess_ms2,

        -- Severity (numeric for calculations)
        CASE condition_flag
            WHEN 'NORMAL'   THEN 0
            WHEN 'WARNING'  THEN 1
            WHEN 'CRITICAL' THEN 2
            ELSE -1
        END AS condition_severity,

        -- Time dimension helpers
        DATE(event_ts)                      AS event_date,
        HOUR(event_ts)                      AS event_hour,
        DAYOFWEEK(event_ts)                 AS event_day_of_week,

        -- Metadata
        CURRENT_TIMESTAMP()                 AS dbt_updated_at

    FROM valid_readings

)

SELECT * FROM enriched
