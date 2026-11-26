{{
    config(
        materialized='view',
        schema='STAGING',
        tags=['staging', 'routing'],
        description='Cleaned market route and container registry data'
    )
}}

/*
============================================================
stg_market_routes.sql – Staging Model
============================================================
Cleans and joins market route data with the container
registry to produce a full route reference.
============================================================
*/

WITH routes AS (
    SELECT
        r.ROUTE_ID                          AS route_id,
        r.CONTAINER_ID                      AS container_id,
        r.ORIGIN_CITY                       AS origin_city,
        r.DESTINATION_CITY                  AS destination_city,
        r.MARKET_NAME                       AS market_name,
        r.IS_ORIGINAL_DEST                  AS is_original_destination,
        r.HOURS_FROM_CURRENT::FLOAT         AS hours_from_current,
        COALESCE(r.DISTANCE_KM, 0.0)::FLOAT AS distance_km,
        r.TRANSPORT_MODE                    AS transport_mode,
        r.REROUTING_COST_USD::FLOAT         AS rerouting_cost_usd
    FROM {{ source('pricing', 'market_routes') }} r
),

containers AS (
    SELECT
        CONTAINER_ID,
        COMMODITY,
        COMMODITY_QUANTITY_KG::FLOAT        AS quantity_kg,
        OPTIMAL_TEMP_MIN::FLOAT             AS optimal_temp_min,
        OPTIMAL_TEMP_MAX::FLOAT             AS optimal_temp_max,
        SHELF_LIFE_DAYS::FLOAT              AS shelf_life_days
    FROM {{ source('pricing', 'container_registry') }}
)

SELECT
    r.route_id,
    r.container_id,
    c.commodity,
    c.quantity_kg,
    c.optimal_temp_min,
    c.optimal_temp_max,
    c.shelf_life_days,
    r.origin_city,
    r.destination_city,
    r.market_name,
    r.is_original_destination,
    r.hours_from_current,
    r.distance_km,
    r.transport_mode,
    r.rerouting_cost_usd,
    CURRENT_TIMESTAMP()                     AS dbt_updated_at

FROM routes r
LEFT JOIN containers c USING (container_id)
