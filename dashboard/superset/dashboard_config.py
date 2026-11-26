"""
============================================================
AtmoSync – Apache Superset Dashboard Configuration
============================================================

WHAT THIS FILE IS:
    Configuration and setup documentation for the AtmoSync
    Apache Superset executive dashboard.

HOW TO ACCESS SUPERSET:
    1. Start: docker-compose up -d superset
    2. Open:  http://localhost:8088
    3. Login: admin / atmosync2024

DASHBOARD SETUP (after Superset is running):
    1. Add Snowflake database connection
    2. Create datasets from mart_container_health
    3. Build the 10 dashboard panels
    4. Configure 5-minute auto-refresh
============================================================
"""

# ============================================================
# STEP 1: SNOWFLAKE DATABASE CONNECTION STRING
# ============================================================
# In Superset UI:
#   Settings > Database Connections > + Database
#   Select: Snowflake
#
# SQLAlchemy URI format:
#   snowflake://{user}:{password}@{account}/{database}/{schema}
#   ?warehouse={warehouse}&role={role}
#
# Example:
#   snowflake://admin:mypass@xy12345.us-east-1/ATMOSYNC_DB/MARTS
#   ?warehouse=ATMOSYNC_WH&role=SYSADMIN
#
# Or use the environment variables from .env

SUPERSET_DB_URI_TEMPLATE = (
    "snowflake://{SNOWFLAKE_USER}:{SNOWFLAKE_PASSWORD}"
    "@{SNOWFLAKE_ACCOUNT}/{SNOWFLAKE_DATABASE}/MARTS"
    "?warehouse={SNOWFLAKE_WAREHOUSE}&role={SNOWFLAKE_ROLE}"
)

# ============================================================
# STEP 2: DASHBOARD DATASETS
# ============================================================
# Create these datasets in Superset from the MARTS schema:
#
# 1. mart_container_health      ← PRIMARY DASHBOARD SOURCE
#    - All container KPIs in one table
#    - Connect: MARTS.mart_container_health
#
# 2. mart_spoilage_analysis
#    - Detailed spoilage calculations
#    - Connect: MARTS.mart_spoilage_analysis
#
# 3. mart_arbitrage_opportunities
#    - Alternative market analysis
#    - Connect: MARTS.mart_arbitrage_opportunities

DATASETS = [
    {
        "name": "Container Health Dashboard",
        "table": "mart_container_health",
        "schema": "MARTS",
        "primary": True,
    },
    {
        "name": "Spoilage Analysis",
        "table": "mart_spoilage_analysis",
        "schema": "MARTS",
    },
    {
        "name": "Arbitrage Opportunities",
        "table": "mart_arbitrage_opportunities",
        "schema": "MARTS",
    },
]

# ============================================================
# STEP 3: DASHBOARD CHART DEFINITIONS
# ============================================================
# Build these 10 charts in Superset:

DASHBOARD_CHARTS = [
    {
        "panel": 1,
        "name": "Container Status Overview",
        "chart_type": "Big Number",
        "dataset": "Container Health Dashboard",
        "metric": "AVG(health_score)",
        "time_column": "last_reading_ts",
        "filters": None,
        "description": "Average fleet health score (0-100)",
    },
    {
        "panel": 2,
        "name": "Temperature Trends by Container",
        "chart_type": "Line Chart",
        "dataset": "Container Health Dashboard",
        "metrics": "AVG(current_temperature_c)",
        "dimensions": ["container_id"],
        "time_column": "last_reading_ts",
        "description": "Temperature readings over time per container",
    },
    {
        "panel": 3,
        "name": "Humidity Trends",
        "chart_type": "Line Chart",
        "dataset": "Container Health Dashboard",
        "metrics": "AVG(current_humidity_pct)",
        "dimensions": ["container_id"],
        "time_column": "last_reading_ts",
        "description": "Humidity trends over time",
    },
    {
        "panel": 4,
        "name": "Vibration Monitor",
        "chart_type": "Bar Chart",
        "dataset": "Container Health Dashboard",
        "metrics": "AVG(current_vibration_ms2)",
        "dimensions": ["container_id"],
        "description": "Average vibration by container",
    },
    {
        "panel": 5,
        "name": "Container Health Indicators",
        "chart_type": "Table",
        "dataset": "Container Health Dashboard",
        "columns": [
            "container_id", "commodity", "container_condition",
            "health_score", "risk_level", "spoilage_score_pct"
        ],
        "description": "Health summary for all containers",
    },
    {
        "panel": 6,
        "name": "At-Risk Container Table",
        "chart_type": "Table",
        "dataset": "Container Health Dashboard",
        "columns": [
            "container_id", "commodity", "risk_level",
            "spoilage_score_pct", "estimated_hours_remaining",
            "will_spoil_before_destination"
        ],
        "filters": "risk_level IN ('HIGH_RISK', 'CRITICAL_RISK')",
        "description": "Containers requiring immediate attention",
    },
    {
        "panel": 7,
        "name": "Spoilage Risk Analysis",
        "chart_type": "Scatter Plot",
        "dataset": "Spoilage Analysis",
        "x_axis": "hours_in_transit",
        "y_axis": "spoilage_score",
        "color": "risk_level",
        "description": "Spoilage score vs transit hours by container",
    },
    {
        "panel": 8,
        "name": "Time-to-Spoilage Indicators",
        "chart_type": "Big Number with Trendline",
        "dataset": "Container Health Dashboard",
        "metric": "MIN(estimated_hours_remaining)",
        "description": "Minimum hours remaining across fleet",
    },
    {
        "panel": 9,
        "name": "Arbitrage Opportunities",
        "chart_type": "Table",
        "dataset": "Arbitrage Opportunities",
        "columns": [
            "container_id", "commodity", "rerouting_recommendation",
            "net_arbitrage_margin_usd", "recommended_alt_market",
            "hours_to_alt_market"
        ],
        "sort": "net_arbitrage_margin_usd DESC",
        "description": "Ranked arbitrage opportunities (mock values)",
    },
    {
        "panel": 10,
        "name": "Alternative Market Recommendations",
        "chart_type": "Table",
        "dataset": "Arbitrage Opportunities",
        "columns": [
            "container_id", "recommended_alt_market", "recommended_alt_city",
            "hours_to_alt_market", "alt_price_usd_per_kg",
            "projected_quality_at_alt_pct", "net_arbitrage_margin_usd"
        ],
        "filters": "rerouting_recommendation = 'RECOMMEND_REROUTE'",
        "description": "Active rerouting recommendations",
    },
]

# ============================================================
# STEP 4: DASHBOARD SETTINGS
# ============================================================

DASHBOARD_CONFIG = {
    "name": "AtmoSync – Container Analytics",
    "refresh_frequency": "5 minutes",
    "default_filters": {
        "risk_level": "All",
        "commodity": "All",
    },
    "layout": "2x5 grid (2 columns, 5 rows)",
}


def print_setup_instructions():
    """Print step-by-step Superset setup instructions."""
    print("=" * 60)
    print("AtmoSync – Superset Dashboard Setup")
    print("=" * 60)
    print()
    print("1. Start Superset:")
    print("   docker-compose up -d superset")
    print()
    print("2. Open: http://localhost:8088")
    print("   Login: admin / atmosync2024")
    print()
    print("3. Add Snowflake connection:")
    print("   Settings > Database Connections > + Database > Snowflake")
    print("   URI: snowflake://USER:PASS@ACCOUNT/ATMOSYNC_DB/MARTS")
    print("        ?warehouse=ATMOSYNC_WH&role=SYSADMIN")
    print()
    print("4. Add datasets (SQL Lab > Datasets):")
    for ds in DATASETS:
        print(f"   - {ds['name']} (MARTS.{ds['table']})")
    print()
    print("5. Create dashboard: Dashboards > + Dashboard")
    print("   Name: 'AtmoSync – Container Analytics'")
    print()
    print("6. Add 10 charts (see DASHBOARD_CHARTS above):")
    for chart in DASHBOARD_CHARTS:
        print(f"   Panel {chart['panel']}: {chart['name']} ({chart['chart_type']})")
    print()
    print("7. Set auto-refresh: Dashboard > ... > Set auto-refresh > 5 min")
    print()
    print("Dashboard ready!")


if __name__ == "__main__":
    print_setup_instructions()
