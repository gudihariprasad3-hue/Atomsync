{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'spoilage', 'analytics'],
        description='Spoilage risk analysis per container with degradation estimates'
    )
}}

/*
============================================================
mart_spoilage_analysis.sql – Analytics Mart Model
============================================================
PURPOSE:
    Calculate spoilage risk, degradation rate, and estimated
    time-to-spoilage for each container.

DISCLAIMER:
    All spoilage calculations in this model use simplified
    mock formulas for demonstration purposes. They are NOT
    scientifically validated spoilage models and should NOT
    be used for real-world commodity decisions.

CALCULATION NOTES:
    Spoilage score (0.0 to 1.0):
      - 0.0 = perfectly fresh
      - 0.7 = spoilage alert threshold
      - 1.0 = fully spoiled

    Temperature contribution:
      Excess degrees above optimal × multiplier × hours in transit

    Humidity contribution:
      Deviation below safe minimum × multiplier

    Vibration contribution:
      Excess vibration above warning threshold × multiplier

    These are MOCK formulas – not real food science models.
============================================================
*/

WITH latest_readings AS (
    -- Get the most recent reading for each container
    SELECT
        container_id,
        commodity,
        origin_location,
        destination_location,
        hours_in_transit,
        temperature_c,
        humidity_pct,
        vibration_ms2,
        temp_deviation_c,
        humidity_deviation_pct,
        vibration_excess_ms2,
        condition_flag,
        has_temp_drift,
        has_humidity_anomaly,
        has_vibration_anomaly,
        condition_severity,
        event_ts,
        ROW_NUMBER() OVER (
            PARTITION BY container_id
            ORDER BY event_ts DESC
        ) AS rn
    FROM {{ ref('stg_sensor_readings') }}
),

current_readings AS (
    SELECT * FROM latest_readings WHERE rn = 1
),

-- Calculate rolling averages for more stable calculations
rolling_averages AS (
    SELECT
        container_id,
        AVG(temperature_c)      AS avg_temperature_c,
        AVG(humidity_pct)       AS avg_humidity_pct,
        AVG(vibration_ms2)      AS avg_vibration_ms2,
        AVG(temp_deviation_c)   AS avg_temp_deviation,
        COUNT(*)                AS total_readings,
        SUM(CASE WHEN condition_flag = 'CRITICAL' THEN 1 ELSE 0 END)
            AS critical_reading_count,
        SUM(CASE WHEN condition_flag = 'WARNING'  THEN 1 ELSE 0 END)
            AS warning_reading_count,
        SUM(CASE WHEN has_temp_drift THEN 1 ELSE 0 END)
            AS temp_drift_events,
        MAX(event_ts)           AS last_reading_ts
    FROM {{ ref('stg_sensor_readings') }}
    GROUP BY container_id
),

-- Join with container route information
container_info AS (
    SELECT
        container_id,
        commodity,
        quantity_kg,
        optimal_temp_min,
        optimal_temp_max,
        shelf_life_days,
        hours_from_current      AS hours_to_original_destination,
        rerouting_cost_usd
    FROM {{ ref('stg_market_routes') }}
    WHERE is_original_destination = TRUE
),

-- Core spoilage calculation
spoilage_calc AS (
    SELECT
        cr.container_id,
        cr.commodity,
        cr.origin_location,
        cr.destination_location,
        cr.hours_in_transit,
        cr.temperature_c         AS current_temp_c,
        cr.humidity_pct          AS current_humidity_pct,
        cr.vibration_ms2         AS current_vibration_ms2,
        cr.condition_flag,
        cr.event_ts              AS last_reading_ts,

        -- Container registry data
        ci.quantity_kg,
        ci.optimal_temp_min,
        ci.optimal_temp_max,
        ci.shelf_life_days,
        ci.hours_to_original_destination,

        -- Rolling averages
        ra.avg_temperature_c,
        ra.avg_temp_deviation,
        ra.total_readings,
        ra.critical_reading_count,
        ra.warning_reading_count,
        ra.temp_drift_events,

        /*
        ====================================================
        MOCK SPOILAGE SCORE CALCULATION
        ====================================================
        Formula (demonstration purposes only):

        spoilage_score = base_transit_spoilage
                       + temperature_contribution
                       + humidity_contribution
                       + vibration_contribution

        Capped between 0.0 and 1.0
        ====================================================
        */

        -- Base spoilage from time in transit (0.02 per hour at optimal)
        LEAST(
            (cr.hours_in_transit / (ci.shelf_life_days * 24.0))
            , 1.0
        ) AS base_transit_spoilage,

        -- Temperature excess contribution
        -- Each degree above optimal × 1.5% per hour
        LEAST(
            (cr.temp_deviation_c * 0.015 * cr.hours_in_transit)
            , 0.5
        ) AS temp_spoilage_contribution,

        -- Humidity deviation contribution
        -- Each % below safe minimum × 0.8% penalty
        LEAST(
            (cr.humidity_deviation_pct * 0.008)
            , 0.2
        ) AS humidity_spoilage_contribution,

        -- Vibration contribution
        -- Excess vibration × 0.05 per m/s²
        LEAST(
            (cr.vibration_excess_ms2 * 0.05)
            , 0.15
        ) AS vibration_spoilage_contribution

    FROM current_readings cr
    LEFT JOIN container_info ci ON cr.container_id = ci.container_id
    LEFT JOIN rolling_averages ra ON cr.container_id = ra.container_id
),

-- Aggregate final spoilage score
final_spoilage AS (
    SELECT
        *,

        -- Total spoilage score (0.0 → 1.0)
        LEAST(
            base_transit_spoilage
            + temp_spoilage_contribution
            + humidity_spoilage_contribution
            + vibration_spoilage_contribution
            , 1.0
        ) AS spoilage_score,

        -- Quality remaining = 1 - spoilage
        1.0 - LEAST(
            base_transit_spoilage
            + temp_spoilage_contribution
            + humidity_spoilage_contribution
            + vibration_spoilage_contribution
            , 1.0
        ) AS quality_remaining_pct,

        -- Estimated remaining shelf hours
        -- Simplified: remaining = (1 - spoilage) × total_shelf_hours × time_factor
        GREATEST(
            (shelf_life_days * 24.0)
            - hours_in_transit
            - (temp_spoilage_contribution * shelf_life_days * 24.0 * 0.5)
            , 0.0
        ) AS estimated_hours_remaining,

        -- Spoilage risk classification
        CASE
            WHEN LEAST(
                base_transit_spoilage + temp_spoilage_contribution
                + humidity_spoilage_contribution + vibration_spoilage_contribution
                , 1.0) >= 0.80 THEN 'CRITICAL_RISK'
            WHEN LEAST(
                base_transit_spoilage + temp_spoilage_contribution
                + humidity_spoilage_contribution + vibration_spoilage_contribution
                , 1.0) >= 0.60 THEN 'HIGH_RISK'
            WHEN LEAST(
                base_transit_spoilage + temp_spoilage_contribution
                + humidity_spoilage_contribution + vibration_spoilage_contribution
                , 1.0) >= 0.35 THEN 'MEDIUM_RISK'
            ELSE 'LOW_RISK'
        END AS risk_level

    FROM spoilage_calc
)

SELECT
    container_id,
    commodity,
    origin_location,
    destination_location,
    hours_in_transit,
    hours_to_original_destination,
    current_temp_c,
    current_humidity_pct,
    current_vibration_ms2,
    condition_flag,
    optimal_temp_min,
    optimal_temp_max,
    avg_temperature_c,
    avg_temp_deviation,
    quantity_kg,

    -- Spoilage metrics
    ROUND(base_transit_spoilage, 4)             AS base_transit_spoilage,
    ROUND(temp_spoilage_contribution, 4)        AS temp_spoilage_contribution,
    ROUND(humidity_spoilage_contribution, 4)    AS humidity_spoilage_contribution,
    ROUND(vibration_spoilage_contribution, 4)   AS vibration_spoilage_contribution,
    ROUND(spoilage_score, 4)                    AS spoilage_score,
    ROUND(quality_remaining_pct, 4)             AS quality_remaining_pct,
    ROUND(estimated_hours_remaining, 1)         AS estimated_hours_remaining,
    risk_level,

    -- Anomaly counts
    total_readings,
    critical_reading_count,
    warning_reading_count,
    temp_drift_events,

    -- Flags
    CASE WHEN estimated_hours_remaining < hours_to_original_destination
         THEN TRUE ELSE FALSE END                AS will_spoil_before_destination,

    last_reading_ts,
    CURRENT_TIMESTAMP()                         AS calculated_at

FROM final_spoilage
