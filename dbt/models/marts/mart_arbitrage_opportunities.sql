{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'arbitrage', 'analytics'],
        description='Arbitrage opportunity analysis with rerouting recommendations'
    )
}}

/*
============================================================
mart_arbitrage_opportunities.sql – Analytics Mart Model
============================================================
PURPOSE:
    Calculate spoilage arbitrage: compare the value of
    the cargo delivered to the original market vs.
    an alternative market, accounting for quality loss,
    rerouting costs, and remaining transit time.

DISCLAIMER:
    All prices, quantities, margins and calculations in
    this model are mock/simulated for demonstration only.
    They are NOT real financial calculations and should
    not be used for actual trading decisions.

ARBITRAGE FORMULA (Mock):
    Original value   = price_original × quantity × quality_at_arrival_original
    Alternative value = price_alt × quantity × quality_at_arrival_alt
    Net arbitrage   = Alternative value - Original value - Rerouting cost

    If net_arbitrage > min_threshold → recommend rerouting
============================================================
*/

WITH spoilage AS (
    SELECT * FROM {{ ref('mart_spoilage_analysis') }}
),

routes AS (
    SELECT * FROM {{ ref('stg_market_routes') }}
),

prices AS (
    SELECT * FROM {{ ref('stg_commodity_prices') }}
),

-- Get original market prices
original_prices AS (
    SELECT
        r.container_id,
        r.market_name       AS original_market,
        r.destination_city  AS original_city,
        r.hours_from_current AS hours_to_original,
        r.rerouting_cost_usd AS original_rerouting_cost,
        p.price_per_unit_usd AS original_price_per_unit
    FROM routes r
    LEFT JOIN prices p
        ON r.commodity = p.commodity
        AND r.market_name = p.market_name
    WHERE r.is_original_destination = TRUE
),

-- Get all alternative market options
alternative_routes AS (
    SELECT
        r.container_id,
        r.market_name       AS alt_market,
        r.destination_city  AS alt_city,
        r.hours_from_current AS hours_to_alt,
        r.rerouting_cost_usd AS rerouting_cost,
        p.price_per_unit_usd AS alt_price_per_unit
    FROM routes r
    LEFT JOIN prices p
        ON r.commodity = p.commodity
        AND r.market_name = p.market_name
    WHERE r.is_original_destination = FALSE
),

-- Calculate quality at each potential destination
-- Based on additional spoilage accumulated during remaining transit
quality_projections AS (
    SELECT
        s.container_id,
        s.commodity,
        s.quantity_kg,
        s.spoilage_score,
        s.quality_remaining_pct,
        s.estimated_hours_remaining,
        s.risk_level,
        s.will_spoil_before_destination,

        op.original_market,
        op.original_city,
        op.hours_to_original,
        op.original_price_per_unit,

        ar.alt_market,
        ar.alt_city,
        ar.hours_to_alt,
        ar.rerouting_cost,
        ar.alt_price_per_unit,

        -- Projected additional spoilage to reach original destination
        -- Additional 0.02 per hour at current degradation rate (mock formula)
        LEAST(
            s.spoilage_score + (op.hours_to_original * 0.02 * (1.0 + s.spoilage_score))
            , 1.0
        ) AS projected_spoilage_at_original,

        -- Projected additional spoilage to reach alternative (fewer hours)
        LEAST(
            s.spoilage_score + (ar.hours_to_alt * 0.02 * (1.0 + s.spoilage_score))
            , 1.0
        ) AS projected_spoilage_at_alt

    FROM spoilage s
    LEFT JOIN original_prices op ON s.container_id = op.container_id
    LEFT JOIN alternative_routes ar ON s.container_id = ar.container_id
),

-- Calculate dollar values and arbitrage margins
arbitrage_calc AS (
    SELECT
        *,

        -- Quality at each market
        ROUND(1.0 - projected_spoilage_at_original, 4) AS quality_at_original,
        ROUND(1.0 - projected_spoilage_at_alt, 4)      AS quality_at_alt,

        -- Revenue calculations (USD)
        -- Original market revenue
        ROUND(
            original_price_per_unit
            * quantity_kg
            * (1.0 - projected_spoilage_at_original)
            , 2
        ) AS original_market_revenue_usd,

        -- Alternative market revenue (before rerouting cost)
        ROUND(
            alt_price_per_unit
            * quantity_kg
            * (1.0 - projected_spoilage_at_alt)
            , 2
        ) AS alt_market_revenue_usd,

        -- Rerouting cost already in the table

        -- Net arbitrage margin = alt_revenue - original_revenue - rerouting_cost
        ROUND(
            (alt_price_per_unit * quantity_kg * (1.0 - projected_spoilage_at_alt))
            - (original_price_per_unit * quantity_kg * (1.0 - projected_spoilage_at_original))
            - rerouting_cost
            , 2
        ) AS net_arbitrage_margin_usd,

        -- Recommendation logic
        CASE
            WHEN (
                -- Will the goods survive to the alternative market?
                estimated_hours_remaining > hours_to_alt
                -- Is the net arbitrage positive and meaningful?
                AND (
                    (alt_price_per_unit * quantity_kg * (1.0 - projected_spoilage_at_alt))
                    - (original_price_per_unit * quantity_kg * (1.0 - projected_spoilage_at_original))
                    - rerouting_cost
                ) > 500.0  -- Minimum $500 margin to recommend rerouting
                -- Not worse quality at alternative
                AND (1.0 - projected_spoilage_at_alt) > 0.3
            ) THEN 'RECOMMEND_REROUTE'
            WHEN risk_level IN ('CRITICAL_RISK', 'HIGH_RISK')
                THEN 'EVALUATE_REROUTE'
            ELSE 'STAY_ON_COURSE'
        END AS rerouting_recommendation

    FROM quality_projections
)

SELECT
    container_id,
    commodity,
    quantity_kg,
    risk_level,
    ROUND(spoilage_score * 100, 1)      AS spoilage_pct,
    ROUND(quality_remaining_pct * 100, 1) AS quality_remaining_pct,
    ROUND(estimated_hours_remaining, 1) AS estimated_hours_remaining,
    will_spoil_before_destination,

    -- Original route
    original_market,
    original_city,
    ROUND(hours_to_original, 1)         AS hours_to_original_market,
    ROUND(original_price_per_unit, 2)   AS original_price_usd_per_kg,
    ROUND(quality_at_original * 100, 1) AS projected_quality_at_original_pct,
    ROUND(original_market_revenue_usd, 0) AS original_revenue_usd,

    -- Alternative route
    alt_market                          AS recommended_alt_market,
    alt_city                            AS recommended_alt_city,
    ROUND(hours_to_alt, 1)              AS hours_to_alt_market,
    ROUND(alt_price_per_unit, 2)        AS alt_price_usd_per_kg,
    ROUND(quality_at_alt * 100, 1)      AS projected_quality_at_alt_pct,
    ROUND(alt_market_revenue_usd, 0)    AS alt_market_revenue_usd,
    ROUND(rerouting_cost, 0)            AS rerouting_cost_usd,
    ROUND(net_arbitrage_margin_usd, 0)  AS net_arbitrage_margin_usd,

    -- Decision
    rerouting_recommendation,

    CURRENT_TIMESTAMP()                 AS calculated_at

FROM arbitrage_calc
ORDER BY net_arbitrage_margin_usd DESC
