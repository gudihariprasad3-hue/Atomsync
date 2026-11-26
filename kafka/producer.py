"""
============================================================
AtmoSync – Kafka Producer (Module B)
============================================================

WHAT THIS DOES:
    Reads sensor events from the simulator and publishes
    them to a Kafka topic. This is the "ingestion" layer –
    it gets data from the source into the pipeline.

WHY KAFKA:
    Kafka handles high-volume, real-time event streams.
    It decouples the simulator (producer) from the
    storage layer (consumer), allowing each to scale
    independently and ensuring no data is lost if the
    consumer is temporarily unavailable.

HOW TO RUN:
    # With Kafka running (docker-compose up -d kafka):
    python kafka/producer.py

    # Test mode (no Kafka required):
    python kafka/producer.py --test
============================================================
"""

import json
import logging
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from config import KAFKA_CONFIG  # kafka/config.py

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PRODUCER] %(levelname)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# PRODUCER CLASS
# ============================================================

class AtmoSyncProducer:
    """
    Kafka producer for AtmoSync sensor events.

    Wraps kafka-python's KafkaProducer with:
      - JSON serialization
      - Error handling and retry logic
      - Message validation before sending
      - Delivery confirmation logging
    """

    def __init__(self, topic: Optional[str] = None):
        self.topic = topic or KAFKA_CONFIG.topic_sensor
        self._producer = None
        self._connected = False
        self._messages_sent = 0
        self._messages_failed = 0

    def connect(self) -> bool:
        """
        Connect to Kafka broker.
        Returns True if successful, False if Kafka is unavailable.
        """
        try:
            from kafka import KafkaProducer
            from kafka.errors import NoBrokersAvailable

            self._producer = KafkaProducer(**KAFKA_CONFIG.producer_config)
            self._connected = True
            logger.info(f"Connected to Kafka at {KAFKA_CONFIG.bootstrap_servers}")
            logger.info(f"Publishing to topic: {self.topic}")
            return True

        except ImportError:
            logger.error("kafka-python not installed. Run: pip install kafka-python")
            return False
        except Exception as e:
            logger.warning(f"Cannot connect to Kafka: {e}")
            logger.warning("Is Kafka running? Start with: docker-compose up -d kafka")
            self._connected = False
            return False

    def _validate_message(self, message: Dict[str, Any]) -> bool:
        """
        Validate message has all required fields before sending.
        Returns True if valid, False otherwise.
        """
        required_fields = [
            "event_id", "container_id", "timestamp",
            "temperature_celsius", "humidity_percent", "vibration_ms2",
            "commodity", "condition",
        ]
        for field in required_fields:
            if field not in message:
                logger.error(f"Message missing required field: {field}")
                return False

        # Type checks
        if not isinstance(message["temperature_celsius"], (int, float)):
            logger.error("temperature_celsius must be numeric")
            return False
        if not isinstance(message["humidity_percent"], (int, float)):
            logger.error("humidity_percent must be numeric")
            return False
        if not (0 <= message["humidity_percent"] <= 100):
            logger.error(f"humidity_percent {message['humidity_percent']} out of range")
            return False

        return True

    def send(self, message: Dict[str, Any]) -> bool:
        """
        Send a single sensor reading to Kafka.

        Args:
            message: Sensor reading dictionary

        Returns:
            True if sent successfully, False otherwise
        """
        if not self._validate_message(message):
            self._messages_failed += 1
            return False

        if not self._connected:
            logger.debug("Not connected to Kafka. Attempting reconnect...")
            if not self.connect():
                self._messages_failed += 1
                return False

        try:
            # Use container_id as partition key for ordered processing
            key = message["container_id"].encode("utf-8")

            future = self._producer.send(
                self.topic,
                key=key,
                value=message,
            )

            # Wait for acknowledgment (with timeout)
            record_metadata = future.get(timeout=10)
            self._messages_sent += 1

            logger.debug(
                f"Sent: {message['container_id']} | "
                f"Partition: {record_metadata.partition} | "
                f"Offset: {record_metadata.offset}"
            )
            return True

        except Exception as e:
            self._messages_failed += 1
            logger.error(f"Failed to send message: {e}")
            self._connected = False
            return False

    def send_batch(self, messages: list) -> Dict[str, int]:
        """
        Send a batch of messages.
        Returns dict with 'sent' and 'failed' counts.
        """
        results = {"sent": 0, "failed": 0}
        for msg in messages:
            if self.send(msg):
                results["sent"] += 1
            else:
                results["failed"] += 1

        # Flush ensures all messages are delivered
        if self._producer and self._connected:
            self._producer.flush()

        return results

    def get_stats(self) -> Dict[str, int]:
        """Return producer statistics."""
        return {
            "messages_sent": self._messages_sent,
            "messages_failed": self._messages_failed,
        }

    def close(self):
        """Flush and close the producer cleanly."""
        if self._producer:
            self._producer.flush()
            self._producer.close()
            logger.info(
                f"Producer closed. "
                f"Sent: {self._messages_sent}, "
                f"Failed: {self._messages_failed}"
            )


# ============================================================
# STANDALONE PRODUCER RUNNER
# ============================================================

def run_producer(test_mode: bool = False, max_messages: Optional[int] = None):
    """
    Run the producer continuously, pulling readings from
    the sensor simulator.
    """
    from simulator.sensor_generator import SensorSimulator
    from simulator.config import SIMULATOR_CONFIG

    simulator = SensorSimulator()
    SIMULATOR_CONFIG.output_to_kafka = False  # Simulator won't send directly
    SIMULATOR_CONFIG.output_to_file = True

    producer = AtmoSyncProducer()

    if not test_mode:
        connected = producer.connect()
        if not connected:
            logger.warning("Running in FILE-ONLY mode (Kafka not available)")

    messages_total = 0
    logger.info("Starting producer loop. Press Ctrl+C to stop.")

    try:
        while True:
            readings = simulator.generate_all_readings()

            if test_mode:
                for r in readings:
                    logger.info(
                        f"[TEST] Would send: {r['container_id']} | "
                        f"Temp={r['temperature_celsius']}°C | "
                        f"Condition={r['condition']}"
                    )
                    messages_total += 1
            else:
                result = producer.send_batch(readings)
                messages_total += result["sent"]
                logger.info(
                    f"Batch sent: {result['sent']} messages | "
                    f"Total: {messages_total}"
                )

            if max_messages and messages_total >= max_messages:
                logger.info(f"Reached max_messages={max_messages}. Stopping.")
                break

            time.sleep(SIMULATOR_CONFIG.interval_seconds)

    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    finally:
        if not test_mode:
            producer.close()
        logger.info(f"Total messages processed: {messages_total}")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AtmoSync Kafka Producer")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: generate readings without sending to Kafka",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Stop after sending this many messages",
    )
    args = parser.parse_args()

    run_producer(test_mode=args.test, max_messages=args.max_messages)
