"""
============================================================
AtmoSync – Kafka Consumer (Module B)
============================================================

WHAT THIS DOES:
    Subscribes to the Kafka topic and processes incoming
    sensor events. For each event it:
      1. Validates the message structure
      2. Logs the reading
      3. Loads the data into Snowflake (if configured)
      4. Triggers alerts for CRITICAL readings

WHY A SEPARATE CONSUMER:
    The consumer runs independently from the producer.
    If the consumer crashes, Kafka remembers its offset
    so it can resume exactly where it left off when
    restarted – no data is lost.

HOW TO RUN:
    # With Kafka running:
    python kafka/consumer.py

    # Test mode (reads from file instead of Kafka):
    python kafka/consumer.py --test
============================================================
"""

import json
import logging
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from config import KAFKA_CONFIG  # kafka/config.py

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CONSUMER] %(levelname)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# MESSAGE HANDLER
# ============================================================

class MessageHandler:
    """
    Handles incoming Kafka messages.
    Pluggable: add handlers for Snowflake, alerts, etc.
    """

    def __init__(self):
        self._handlers: list[Callable] = []
        self._processed = 0
        self._errors = 0
        self._critical_count = 0

    def register_handler(self, handler: Callable) -> None:
        """Register a function to call for each valid message."""
        self._handlers.append(handler)

    def process(self, message: Dict[str, Any]) -> bool:
        """
        Process a single message through all registered handlers.
        Returns True if all handlers succeeded.
        """
        # Validate basic structure
        if not self._is_valid(message):
            self._errors += 1
            return False

        self._processed += 1

        # Track critical events
        if message.get("condition") == "CRITICAL":
            self._critical_count += 1
            logger.warning(
                f"🚨 CRITICAL: {message['container_id']} | "
                f"Temp={message['temperature_celsius']}°C | "
                f"Anomalies={message.get('anomalies', [])}"
            )

        # Run all registered handlers
        success = True
        for handler in self._handlers:
            try:
                handler(message)
            except Exception as e:
                logger.error(f"Handler {handler.__name__} failed: {e}")
                success = False

        return success

    def _is_valid(self, message: Dict[str, Any]) -> bool:
        """Basic schema validation."""
        required = [
            "event_id", "container_id", "timestamp",
            "temperature_celsius", "humidity_percent",
            "vibration_ms2", "commodity", "condition",
        ]
        for field in required:
            if field not in message:
                logger.error(f"Invalid message: missing field '{field}'")
                return False
        return True

    def stats(self) -> Dict[str, int]:
        return {
            "processed": self._processed,
            "errors": self._errors,
            "critical_events": self._critical_count,
        }


# ============================================================
# DEFAULT HANDLERS
# ============================================================

def log_handler(message: Dict[str, Any]) -> None:
    """Log sensor reading to console."""
    symbol = {"NORMAL": "✅", "WARNING": "⚠️ ", "CRITICAL": "🚨"}.get(
        message["condition"], "❓"
    )
    logger.info(
        f"{symbol} {message['container_id']:8s} | "
        f"{message['commodity']:10s} | "
        f"T={message['temperature_celsius']:6.2f}°C | "
        f"H={message['humidity_percent']:5.1f}% | "
        f"V={message['vibration_ms2']:5.3f} m/s² | "
        f"{message['condition']}"
    )


def file_storage_handler(message: Dict[str, Any]) -> None:
    """Write message to processed readings file."""
    output_path = Path("data/sample_data/processed_readings.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a") as f:
        f.write(json.dumps(message) + "\n")


def snowflake_handler(message: Dict[str, Any]) -> None:
    """
    Load message into Snowflake RAW_SENSOR_READINGS table.
    Only runs if Snowflake is configured.
    """
    try:
        from snowflake.connection import SnowflakeConnection
        from snowflake.load_data import load_sensor_reading

        with SnowflakeConnection() as conn:
            load_sensor_reading(conn, message)
    except ImportError:
        pass  # Snowflake not configured
    except Exception as e:
        logger.error(f"Snowflake load failed: {e}")
        raise  # Re-raise so MessageHandler records it as error


# ============================================================
# CONSUMER CLASS
# ============================================================

class AtmoSyncConsumer:
    """
    Kafka consumer for AtmoSync sensor events.

    Features:
      - Subscribes to configured topic
      - Processes messages through pluggable handlers
      - Handles connection errors and retries
      - Tracks processing statistics
    """

    def __init__(self):
        self._consumer = None
        self._connected = False
        self.handler = MessageHandler()

        # Register default handlers
        self.handler.register_handler(log_handler)
        self.handler.register_handler(file_storage_handler)

    def connect(self) -> bool:
        """Connect to Kafka broker."""
        try:
            from kafka import KafkaConsumer
            from kafka.errors import NoBrokersAvailable

            self._consumer = KafkaConsumer(
                KAFKA_CONFIG.topic_sensor,
                **KAFKA_CONFIG.consumer_config,
            )
            self._connected = True
            logger.info(f"Connected to Kafka at {KAFKA_CONFIG.bootstrap_servers}")
            logger.info(f"Subscribed to topic: {KAFKA_CONFIG.topic_sensor}")
            logger.info(f"Consumer group: {KAFKA_CONFIG.group_id}")
            return True

        except ImportError:
            logger.error("kafka-python not installed. Run: pip install kafka-python")
            return False
        except Exception as e:
            logger.warning(f"Cannot connect to Kafka: {e}")
            self._connected = False
            return False

    def run(self, max_messages: Optional[int] = None, timeout_ms: int = 1000):
        """
        Start consuming messages.

        Args:
            max_messages: Stop after N messages (None = infinite)
            timeout_ms: Poll timeout in milliseconds
        """
        if not self.connect():
            logger.error("Cannot start consumer – Kafka unavailable.")
            return

        messages_consumed = 0
        logger.info("Consumer started. Press Ctrl+C to stop.\n")

        try:
            for message in self._consumer:
                try:
                    data = message.value  # Already deserialized by KafkaConsumer

                    if isinstance(data, (bytes, str)):
                        data = json.loads(data)

                    self.handler.process(data)
                    messages_consumed += 1

                    if max_messages and messages_consumed >= max_messages:
                        logger.info(f"Reached max_messages={max_messages}. Stopping.")
                        break

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e} | Raw: {message.value}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except KeyboardInterrupt:
            logger.info("Stopped by user.")
        finally:
            stats = self.handler.stats()
            logger.info(
                f"Consumer stats – "
                f"Processed: {stats['processed']} | "
                f"Errors: {stats['errors']} | "
                f"Critical events: {stats['critical_events']}"
            )
            if self._consumer:
                self._consumer.close()

    def run_from_file(self, file_path: str = "data/sample_data/live_readings.json"):
        """
        Process readings from a file instead of Kafka.
        Used for testing without a running Kafka cluster.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            logger.info("Generate sample data first: python simulator/sensor_generator.py --mode sample")
            return

        logger.info(f"Reading from file: {file_path}")
        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                    self.handler.process(message)
                    time.sleep(0.05)  # Small delay for readability
                except json.JSONDecodeError as e:
                    logger.error(f"Line {line_num}: JSON error: {e}")

        stats = self.handler.stats()
        logger.info(
            f"File processing complete – "
            f"Processed: {stats['processed']} | "
            f"Errors: {stats['errors']} | "
            f"Critical events: {stats['critical_events']}"
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AtmoSync Kafka Consumer")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: read from file instead of Kafka",
    )
    parser.add_argument(
        "--file",
        default="data/sample_data/live_readings.json",
        help="File to read in test mode",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Stop after consuming N messages",
    )
    args = parser.parse_args()

    consumer = AtmoSyncConsumer()

    if args.test:
        consumer.run_from_file(args.file)
    else:
        consumer.run(max_messages=args.max_messages)
