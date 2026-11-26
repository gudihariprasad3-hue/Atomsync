#!/bin/bash
# ============================================================
# AtmoSync – Apache Superset Initialization Script
# ============================================================
# Run this ONCE after Superset starts for the first time.
#
# Usage (from project root):
#   docker-compose exec superset bash /app/init_superset.sh
#
# Or manually in the Superset container:
#   docker exec -it atmosync-superset bash /app/init_superset.sh
# ============================================================

set -e

echo "============================================================"
echo "AtmoSync – Initializing Apache Superset"
echo "============================================================"

# 1. Upgrade database schema
echo "[1/5] Upgrading Superset DB schema..."
superset db upgrade

# 2. Create admin user
echo "[2/5] Creating admin user..."
superset fab create-admin \
  --username admin \
  --firstname AtmoSync \
  --lastname Admin \
  --email admin@atmosync.local \
  --password atmosync2024 || echo "Admin user may already exist – skipping."

# 3. Load default roles and permissions
echo "[3/5] Loading default roles..."
superset init

# 4. Load example dashboards (optional – helps with initial UI orientation)
# Uncomment to include Superset example data:
# superset load_examples

echo "[4/5] Setting up complete."

# 5. Done
echo "============================================================"
echo "Superset initialized successfully!"
echo ""
echo "Access the dashboard at: http://localhost:8088"
echo "Login: admin / atmosync2024"
echo ""
echo "Next steps:"
echo "  1. Settings > Database Connections > + Database > Snowflake"
echo "  2. Add URI: snowflake://USER:PASS@ACCOUNT/ATMOSYNC_DB/MARTS"
echo "  3. Add datasets from MARTS schema (mart_container_health, etc.)"
echo "  4. Build dashboard panels per dashboard/superset/dashboard_config.py"
echo "============================================================"
