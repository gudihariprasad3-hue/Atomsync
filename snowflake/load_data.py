"""
============================================================
AtmoSync – Snowflake Data Loader (Module C)
============================================================
Utilities for loading sensor readings and pricing data
into Snowflake tables.
============================================================
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# SENSOR READING LOADER
# ============================================================

def load_sensor_reading(conn, reading: Dict[str, Any]) -> bool:
    """
    Insert a single sensor reading into RAW.RAW_SENSOR_READINGS.

    Args:
        conn: Active Snowflake connection object
        reading: Sensor reading dictionary from simulator

    Returns:
        True if inserted successfully
    """
    sql = """
    INSERT INTO ATMOSYNC_DB.RAW.RAW_SENSOR_READINGS (
        EVENT_ID, CONTAINER_ID, EVENT_TIMESTAMP,
        TEMPERATURE_CELSIUS, HUMIDITY_PERCENT, VIBRATION_MS2,
        COMMODITY, ORIGIN, DESTINATION, HOURS_IN_TRANSIT,
        CONDITION, ANOMALIES, RAW_PAYLOAD, THRESHOLDS
    ) VALUES (
        %(event_id)s,
        %(container_id)s,
        %(timestamp)s::TIMESTAMP_TZ,
        %(temperature_celsius)s,
        %(humidity_percent)s,
        %(vibration_ms2)s,
        %(commodity)s,
        %(origin)s,
        %(destination)s,
        %(hours_in_transit)s,
        %(condition)s,
        PARSE_JSON(%(anomalies_json)s),
        PARSE_JSON(%(raw_payload)s),
        PARSE_JSON(%(thresholds_json)s)
    )
    """

    params = {
        "event_id": reading["event_id"],
        "container_id": reading["container_id"],
        "timestamp": reading["timestamp"],
        "temperature_celsius": reading["temperature_celsius"],
        "humidity_percent": reading["humidity_percent"],
        "vibration_ms2": reading["vibration_ms2"],
        "commodity": reading["commodity"],
        "origin": reading.get("origin", ""),
        "destination": reading.get("destination", ""),
        "hours_in_transit": reading.get("hours_in_transit", 0.0),
        "condition": reading.get("condition", "UNKNOWN"),
        "anomalies_json": json.dumps(reading.get("anomalies", [])),
        "raw_payload": json.dumps(reading),
        "thresholds_json": json.dumps(reading.get("thresholds", {})),
    }

    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return True
    except Exception as e:
        logger.error(f"Failed to insert reading {reading.get('event_id')}: {e}")
        return False


def load_readings_batch(conn, readings: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Insert multiple sensor readings in a batch.
    Returns counts of successes and failures.
    """
    results = {"inserted": 0, "failed": 0}
    for reading in readings:
        if load_sensor_reading(conn, reading):
            results["inserted"] += 1
        else:
            results["failed"] += 1

    logger.info(
        f"Batch load complete: "
        f"{results['inserted']} inserted, {results['failed']} failed"
    )
    return results


def load_readings_from_file(
    file_path: str = "data/sample_data/sample_readings.json",
    max_rows: Optional[int] = None,
) -> Dict[str, int]:
    """
    Load sensor readings from a JSONL file into Snowflake.
    Used for initial data seeding or replaying readings.
    """
    from snowflake_conn import SnowflakeConnection

    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return {"inserted": 0, "failed": 0, "error": 1}

    readings = []
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                readings.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.error(f"Line {line_num}: {e}")

            if max_rows and len(readings) >= max_rows:
                break

    logger.info(f"Loaded {len(readings)} readings from file. Inserting into Snowflake...")

    with SnowflakeConnection(schema="RAW") as conn:
        return load_readings_batch(conn, readings)


# ============================================================
# SNOWFLAKE LOAD TEST
# ============================================================

def test_data_loading():
    """
    Test that data can be loaded into Snowflake.
    Uses a synthetic test reading.
    """
    import uuid
    from snowflake_conn import SnowflakeConnection

    print("=" * 60)
    print("AtmoSync – Snowflake Data Load Test")
    print("=" * 60)

    test_reading = {
        "event_id": str(uuid.uuid4()),
        "container_id": "CTR-TEST",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "temperature_celsius": 6.5,
        "humidity_percent": 90.0,
        "vibration_ms2": 0.3,
        "commodity": "AVOCADO",
        "origin": "Test Origin",
        "destination": "Test Destination",
        "hours_in_transit": 1.0,
        "condition": "NORMAL",
        "anomalies": [],
        "thresholds": {
            "temp_min": 2.0, "temp_max": 8.0,
            "humidity_min": 85.0, "humidity_max": 95.0,
            "vibration_warning": 1.5,
        },
    }

    try:
        with SnowflakeConnection(schema="RAW") as conn:
            success = load_sensor_reading(conn, test_reading)
            if success:
                # Verify it was inserted
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM RAW_SENSOR_READINGS WHERE EVENT_ID = %s",
                    (test_reading["event_id"],)
                )
                count = cursor.fetchone()[0]
                if count == 1:
                    print(f"✅ Test reading inserted and verified in Snowflake!")
                    print(f"   Event ID: {test_reading['event_id']}")
                    return True
                else:
                    print("❌ FAIL: Reading not found after insert")
                    return False
            else:
                print("❌ FAIL: Insert failed")
                return False
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_data_loading()
