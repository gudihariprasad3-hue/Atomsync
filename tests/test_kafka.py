"""
============================================================
AtmoSync – Kafka Tests
============================================================
Run with: pytest tests/test_kafka.py -v
NOTE: Most tests run without a live Kafka broker.
      Integration tests require docker-compose up -d kafka
============================================================
"""

import json
import sys
import uuid
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix import path for kafka module
sys.path.insert(0, str(Path(__file__).parent.parent / "kafka"))

from kafka.producer import AtmoSyncProducer
from kafka.consumer import AtmoSyncConsumer, MessageHandler, log_handler


# ============================================================
# TEST FIXTURES
# ============================================================

@pytest.fixture
def valid_message():
    """A valid sensor message."""
    return {
        "event_id": str(uuid.uuid4()),
        "container_id": "CTR-001",
        "timestamp": "2026-11-24T10:00:00+00:00",
        "temperature_celsius": 5.5,
        "humidity_percent": 90.0,
        "vibration_ms2": 0.3,
        "commodity": "AVOCADO",
        "condition": "NORMAL",
        "anomalies": [],
    }


@pytest.fixture
def invalid_message_missing_field():
    """A message missing a required field."""
    return {
        "event_id": str(uuid.uuid4()),
        "container_id": "CTR-001",
        # Missing: timestamp, temperature_celsius, etc.
    }


@pytest.fixture
def producer():
    """Return a producer instance (not connected to Kafka)."""
    return AtmoSyncProducer()


@pytest.fixture
def consumer():
    """Return a consumer instance (not connected to Kafka)."""
    return AtmoSyncConsumer()


# ============================================================
# PRODUCER TESTS
# ============================================================

class TestProducerMessageValidation:
    """Test producer-side message validation."""

    def test_valid_message_passes_validation(self, producer, valid_message):
        """A properly formed message should pass validation."""
        result = producer._validate_message(valid_message)
        assert result is True

    def test_missing_event_id_fails(self, producer, valid_message):
        """Message without event_id should fail validation."""
        del valid_message["event_id"]
        result = producer._validate_message(valid_message)
        assert result is False

    def test_missing_container_id_fails(self, producer, valid_message):
        """Message without container_id should fail validation."""
        del valid_message["container_id"]
        result = producer._validate_message(valid_message)
        assert result is False

    def test_missing_temperature_fails(self, producer, valid_message):
        """Message without temperature_celsius should fail validation."""
        del valid_message["temperature_celsius"]
        result = producer._validate_message(valid_message)
        assert result is False

    def test_non_numeric_temperature_fails(self, producer, valid_message):
        """Temperature must be numeric."""
        valid_message["temperature_celsius"] = "hot"
        result = producer._validate_message(valid_message)
        assert result is False

    def test_humidity_out_of_range_fails(self, producer, valid_message):
        """Humidity > 100 should fail validation."""
        valid_message["humidity_percent"] = 110.0
        result = producer._validate_message(valid_message)
        assert result is False

    def test_missing_all_sensor_fields_fails(self, producer):
        """An empty message should fail."""
        result = producer._validate_message({})
        assert result is False


class TestProducerStats:
    """Test producer statistics tracking."""

    def test_initial_stats_are_zero(self, producer):
        """New producer should have zero sent/failed counts."""
        stats = producer.get_stats()
        assert stats["messages_sent"] == 0
        assert stats["messages_failed"] == 0

    def test_failed_validation_increments_failed_count(self, producer):
        """Sending an invalid message should increment failed count."""
        invalid = {"bad": "message"}
        producer._connected = True  # Pretend connected
        producer._producer = MagicMock()

        producer.send(invalid)
        assert producer._messages_failed == 1

    def test_producer_connect_failure_does_not_crash(self, producer):
        """Connection failure should return False, not raise an exception."""
        # Will try to connect to localhost:9092 and fail gracefully
        result = producer.connect()
        assert isinstance(result, bool)


# ============================================================
# MESSAGE HANDLER TESTS
# ============================================================

class TestMessageHandler:
    """Test the consumer message handler."""

    def test_valid_message_is_processed(self, valid_message):
        """A valid message should be processed without errors."""
        handler = MessageHandler()
        result = handler.process(valid_message)
        assert result is True
        assert handler.stats()["processed"] == 1

    def test_invalid_message_increments_error(self, invalid_message_missing_field):
        """An invalid message should increment the error counter."""
        handler = MessageHandler()
        result = handler.process(invalid_message_missing_field)
        assert result is False
        assert handler.stats()["errors"] == 1

    def test_critical_message_increments_critical_count(self):
        """A CRITICAL condition message should increment critical_events."""
        handler = MessageHandler()
        critical_msg = {
            "event_id": str(uuid.uuid4()),
            "container_id": "CTR-001",
            "timestamp": "2026-11-24T10:00:00+00:00",
            "temperature_celsius": 20.0,
            "humidity_percent": 60.0,
            "vibration_ms2": 3.5,
            "commodity": "AVOCADO",
            "condition": "CRITICAL",
            "anomalies": ["TEMPERATURE_DRIFT"],
        }
        handler.process(critical_msg)
        assert handler.stats()["critical_events"] == 1

    def test_handler_registration_and_callback(self, valid_message):
        """Registered handlers should be called for each valid message."""
        called_with = []

        def test_handler(msg):
            called_with.append(msg["container_id"])

        handler = MessageHandler()
        handler.register_handler(test_handler)
        handler.process(valid_message)

        assert "CTR-001" in called_with

    def test_multiple_messages_accumulate_stats(self, valid_message):
        """Processing multiple messages should accumulate correctly."""
        handler = MessageHandler()

        for _ in range(5):
            msg = {**valid_message, "event_id": str(uuid.uuid4())}
            handler.process(msg)

        assert handler.stats()["processed"] == 5


# ============================================================
# CONSUMER FILE MODE TEST
# ============================================================

class TestConsumerFileMode:
    """Test consumer reading from file (no Kafka required)."""

    def test_consumer_reads_from_valid_file(self, tmp_path, valid_message):
        """Consumer should process all lines from a JSONL file."""
        # Write test messages to file
        test_file = tmp_path / "test_readings.json"
        with open(test_file, "w") as f:
            for i in range(3):
                msg = {**valid_message, "event_id": str(uuid.uuid4())}
                f.write(json.dumps(msg) + "\n")

        # Create consumer with custom handler to capture results
        consumer = AtmoSyncConsumer()
        # Remove default handlers
        consumer.handler._handlers = []

        processed = []
        consumer.handler.register_handler(lambda m: processed.append(m))
        consumer.run_from_file(str(test_file))

        assert len(processed) == 3

    def test_consumer_handles_nonexistent_file_gracefully(self):
        """Consumer should log error but not crash on missing file."""
        consumer = AtmoSyncConsumer()
        consumer.handler._handlers = []

        # Should not raise an exception
        consumer.run_from_file("/nonexistent/path/file.json")

    def test_consumer_handles_malformed_json_line(self, tmp_path, valid_message):
        """Consumer should skip malformed lines without stopping."""
        test_file = tmp_path / "mixed_readings.json"
        with open(test_file, "w") as f:
            f.write(json.dumps(valid_message) + "\n")
            f.write("THIS IS NOT JSON\n")
            msg2 = {**valid_message, "event_id": str(uuid.uuid4())}
            f.write(json.dumps(msg2) + "\n")

        consumer = AtmoSyncConsumer()
        consumer.handler._handlers = []

        processed = []
        consumer.handler.register_handler(lambda m: processed.append(m))
        consumer.run_from_file(str(test_file))

        # Should process 2 valid messages, skip 1 malformed
        assert len(processed) == 2
