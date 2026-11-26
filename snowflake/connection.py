"""
============================================================
AtmoSync – Snowflake Connection Manager (Module C)
============================================================

WHAT THIS DOES:
    Provides a secure, reusable connection to Snowflake.
    All credentials come from environment variables in .env.
    Never hardcodes any credentials.

HOW TO TEST THE CONNECTION:
    python snowflake/connection.py

HOW TO USE IN CODE:
    from snowflake.connection import SnowflakeConnection

    with SnowflakeConnection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_VERSION()")
        print(cursor.fetchone())
============================================================
"""

import os
import sys
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

class SnowflakeConfig:
    """
    Reads all Snowflake credentials from environment variables.
    Never stores credentials in source code.
    """

    def __init__(self):
        self.account   = os.getenv("SNOWFLAKE_ACCOUNT", "")
        self.user      = os.getenv("SNOWFLAKE_USER", "")
        self.password  = os.getenv("SNOWFLAKE_PASSWORD", "")
        self.database  = os.getenv("SNOWFLAKE_DATABASE", "ATMOSYNC_DB")
        self.schema    = os.getenv("SNOWFLAKE_SCHEMA", "RAW")
        self.warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "ATMOSYNC_WH")
        self.role      = os.getenv("SNOWFLAKE_ROLE", "SYSADMIN")

    def is_configured(self) -> bool:
        """Check if all required credentials are present."""
        return bool(self.account and self.user and self.password)

    def masked_summary(self) -> str:
        """Return a safe summary (passwords masked)."""
        return (
            f"Account:   {self.account or '(NOT SET)'}\n"
            f"User:      {self.user or '(NOT SET)'}\n"
            f"Password:  {'*' * 8 if self.password else '(NOT SET)'}\n"
            f"Database:  {self.database}\n"
            f"Schema:    {self.schema}\n"
            f"Warehouse: {self.warehouse}\n"
            f"Role:      {self.role}"
        )


SNOWFLAKE_CONFIG = SnowflakeConfig()


# ============================================================
# CONNECTION CLASS
# ============================================================

class SnowflakeConnection:
    """
    Context-manager wrapper around snowflake-connector-python.

    Usage:
        with SnowflakeConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
    """

    def __init__(self, schema: Optional[str] = None):
        self.config = SNOWFLAKE_CONFIG
        self.schema = schema or self.config.schema
        self._conn = None

    def __enter__(self):
        self.connect()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Don't suppress exceptions

    def connect(self):
        """
        Open connection to Snowflake.
        Raises ConnectionError if credentials are missing.
        """
        if not self.config.is_configured():
            raise ConnectionError(
                "Snowflake credentials not configured.\n"
                "Please copy .env.example to .env and fill in:\n"
                "  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD"
            )

        try:
            import snowflake.connector as sf

            self._conn = sf.connect(
                account=self.config.account,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                schema=self.schema,
                warehouse=self.config.warehouse,
                role=self.config.role,
                # Connection pooling settings
                session_parameters={
                    "QUERY_TAG": "AtmoSync-Pipeline",
                    "TIMEZONE": "UTC",
                },
            )
            logger.info(
                f"Connected to Snowflake: "
                f"{self.config.account}/{self.config.database}/{self.schema}"
            )
            return self._conn

        except ImportError:
            raise ImportError(
                "snowflake-connector-python not installed.\n"
                "Run: pip install snowflake-connector-python"
            )
        except Exception as e:
            raise ConnectionError(f"Snowflake connection failed: {e}")

    def close(self):
        """Close the Snowflake connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Snowflake connection closed.")

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> list:
        """
        Execute a SQL query and return all results.

        Args:
            sql: SQL query string
            params: Optional tuple of parameters for parameterized queries

        Returns:
            List of row tuples
        """
        with self as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()

    def execute_statement(self, sql: str, params: Optional[tuple] = None) -> int:
        """
        Execute a DML statement (INSERT, UPDATE, DELETE).
        Returns the number of rows affected.
        """
        with self as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.rowcount


# ============================================================
# CONNECTION TEST
# ============================================================

def test_connection() -> bool:
    """
    Test the Snowflake connection and print results.
    Returns True if connection is successful.
    """
    print("=" * 60)
    print("AtmoSync – Snowflake Connection Test")
    print("=" * 60)
    print("\nConfiguration:")
    print(SNOWFLAKE_CONFIG.masked_summary())
    print()

    if not SNOWFLAKE_CONFIG.is_configured():
        print("❌ FAIL: Credentials not configured.")
        print("   Copy .env.example to .env and fill in your Snowflake details.")
        return False

    try:
        import snowflake.connector as sf

        conn = sf.connect(
            account=SNOWFLAKE_CONFIG.account,
            user=SNOWFLAKE_CONFIG.user,
            password=SNOWFLAKE_CONFIG.password,
            database=SNOWFLAKE_CONFIG.database,
            schema=SNOWFLAKE_CONFIG.schema,
            warehouse=SNOWFLAKE_CONFIG.warehouse,
        )

        cursor = conn.cursor()

        # Basic connectivity test
        cursor.execute("SELECT CURRENT_VERSION(), CURRENT_USER(), CURRENT_DATABASE()")
        version, user, database = cursor.fetchone()
        print(f"✅ Connected successfully!")
        print(f"   Snowflake version: {version}")
        print(f"   Current user:      {user}")
        print(f"   Current database:  {database}")

        # Check tables exist
        cursor.execute("SHOW TABLES IN SCHEMA ATMOSYNC_DB.RAW")
        tables = cursor.fetchall()
        table_names = [t[1] for t in tables] if tables else []
        print(f"\nTables in RAW schema: {table_names or 'None (run schema.sql first)'}")

        cursor.execute("SELECT COUNT(*) FROM ATMOSYNC_DB.PRICING.CONTAINER_REGISTRY")
        count = cursor.fetchone()[0]
        print(f"Container registry rows: {count}")

        conn.close()
        print("\n✅ All connection tests passed!")
        return True

    except ImportError:
        print("❌ FAIL: snowflake-connector-python not installed.")
        print("   Run: pip install snowflake-connector-python")
        return False
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = test_connection()
    sys.exit(0 if success else 1)
