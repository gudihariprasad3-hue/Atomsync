{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'monitoring', 'dashboard'],
        description='Container health dashboard view with KPIs for Superset'
    )
}}

/*
============================================================
mart_container_health.sql – Dashboard Mart Model
============================================================
PURPOSE:
    Provides a denormalized, dashboard-ready view of all
    container health metrics in a single table. This is
    the primary table that Apache Superset queries.
============================================================
*/

WITH spoilage AS (
    SELECT * FROM {{ ref('mart_spoilage_analysis') }}
),

arbitrage AS (
    -- Best arbitrage opportunity per container
    SELECT
        container_id,
        MAX(net_arbitrage_margin_usd)   AS best_arbitrage_usd,
        MAX(CASE WHEN rerouting_recommendation = 'RECOMMEND_REROUTE'
                 THEN recommended_alt_market END)
            AS recommended_market,
        MAX(CASE WHEN rerouting_recommendation = 'RECOMMEND_REROUTE'
                 THEN recommended_alt_city END)
            AS recommended_city,
        MAX(CASE WHEN rerouting_recommendation = 'RECOMMEND_REROUTE'
                 THEN hours_to_alt_market END)
            AS hours_to_recommended_market,
        MAX(rerouting_recommendation)   AS best_recommendation
    FROM {{ ref('mart_arbitrage_opportunities') }}
    GROUP BY container_id
)

SELECT
    s.container_id,
    s.commodity,
    s.origin_location,
    s.destination_location,
    s.hours_in_transit,
    s.hours_to_original_destination,

    -- Current sensors
    ROUND(s.current_temp_c, 2)              AS current_temperature_c,
    ROUND(s.current_humidity_pct, 1)        AS current_humidity_pct,
    ROUND(s.current_vibration_ms2, 3)       AS current_vibration_ms2,
    s.condition_flag                        AS container_condition,

    -- Optimal ranges
    s.optimal_temp_min,
    s.optimal_temp_max,
    ROUND(s.avg_temperature_c, 2)           AS avg_temperature_c,

    -- Spoilage
    ROUND(s.spoilage_score * 100, 1)        AS spoilage_score_pct,
    ROUND(s.quality_remaining_pct * 100, 1) AS quality_remaining_pct,
    ROUND(s.estimated_hours_remaining, 1)   AS estimated_hours_remaining,
    s.risk_level,
    s.will_spoil_before_destination,

    -- Anomaly counts
    s.total_readings,
    s.critical_reading_count,
    s.warning_reading_count,
    s.temp_drift_events,

    -- Arbitrage
    ROUND(a.best_arbitrage_usd, 0)          AS best_arbitrage_margin_usd,
    a.recommended_market,
    a.recommended_city,
    a.hours_to_recommended_market,
    a.best_recommendation,

    -- Health score (composite 0-100, higher = better)
    ROUND(
        (s.quality_remaining_pct * 60.0)
        + (CASE s.condition_flag
             WHEN 'NORMAL'   THEN 30.0
             WHEN 'WARNING'  THEN 10.0
             WHEN 'CRITICAL' THEN 0.0
             ELSE 5.0
           END)
        + (CASE WHEN s.temp_drift_events = 0 THEN 10.0
                WHEN s.temp_drift_events < 3 THEN 5.0
                ELSE 0.0
           END)
    * 100.0 / 100.0, 1
    ) AS health_score,

    -- Time KPIs
    s.last_reading_ts,
    DATEDIFF(minute, s.last_reading_ts, CURRENT_TIMESTAMP()) AS minutes_since_last_reading,
    s.calculated_at

FROM spoilage s
LEFT JOIN arbitrage a ON s.container_id = a.container_id
