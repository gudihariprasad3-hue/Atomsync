{{
    config(
        materialized='view',
        schema='STAGING',
        tags=['staging', 'pricing'],
        description='Cleaned commodity pricing reference data'
    )
}}

/*
============================================================
stg_commodity_prices.sql – Staging Model
============================================================
DISCLAIMER: All prices in this model are mock data
created for demonstration purposes only. They do not
represent real market prices.
============================================================
*/

SELECT
    PRICE_ID                        AS price_id,
    UPPER(TRIM(COMMODITY))          AS commodity,
    MARKET_NAME                     AS market_name,
    CITY                            AS market_city,
    PRICE_PER_UNIT_USD::FLOAT       AS price_per_unit_usd,
    EFFECTIVE_DATE                  AS price_date,
    IS_ACTIVE                       AS is_active,
    NOTES                           AS notes,
    CURRENT_TIMESTAMP()             AS dbt_updated_at

FROM {{ source('pricing', 'commodity_prices') }}
WHERE IS_ACTIVE = TRUE
