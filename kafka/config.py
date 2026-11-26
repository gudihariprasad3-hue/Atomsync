"""
============================================================
AtmoSync – Kafka Configuration (Module B)
============================================================
All Kafka connection settings loaded from environment
variables. Never hardcode connection details.
============================================================
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


@dataclass
class KafkaConfig:
    """Kafka connection and topic configuration."""

    # Broker connection
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    # Topics
    topic_sensor: str = os.getenv("KAFKA_TOPIC_SENSOR", "atmosync-sensor-events")
    topic_alerts: str = os.getenv("KAFKA_TOPIC_ALERTS", "atmosync-alerts")

    # Consumer group
    group_id: str = os.getenv("KAFKA_GROUP_ID", "atmosync-consumer-group")

    # Producer settings
    producer_acks: str = "all"           # Wait for all replicas to acknowledge
    producer_retries: int = 3
    producer_linger_ms: int = 10         # Slight batching delay (ms)
    producer_batch_size: int = 16384     # 16KB batch size

    # Consumer settings
    consumer_auto_offset_reset: str = "earliest"   # Start from beginning if no offset
    consumer_enable_auto_commit: bool = True
    consumer_auto_commit_interval_ms: int = 1000
    consumer_max_poll_records: int = 100
    consumer_session_timeout_ms: int = 30000

    # Serialization
    value_serializer_encoding: str = "utf-8"

    # Retry/timeout
    request_timeout_ms: int = 30000
    metadata_max_age_ms: int = 300000

    @property
    def producer_config(self) -> dict:
        """Return dict for kafka-python KafkaProducer."""
        import json
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "value_serializer": lambda v: json.dumps(v).encode(self.value_serializer_encoding),
            "acks": self.producer_acks,
            "retries": self.producer_retries,
            "linger_ms": self.producer_linger_ms,
            "batch_size": self.producer_batch_size,
            "request_timeout_ms": self.request_timeout_ms,
        }

    @property
    def consumer_config(self) -> dict:
        """Return dict for kafka-python KafkaConsumer."""
        import json
        return {
            "bootstrap_servers": self.bootstrap_servers,
            "group_id": self.group_id,
            "value_deserializer": lambda v: json.loads(v.decode(self.value_serializer_encoding)),
            "auto_offset_reset": self.consumer_auto_offset_reset,
            "enable_auto_commit": self.consumer_enable_auto_commit,
            "auto_commit_interval_ms": self.consumer_auto_commit_interval_ms,
            "max_poll_records": self.consumer_max_poll_records,
            "session_timeout_ms": self.consumer_session_timeout_ms,
            "request_timeout_ms": self.request_timeout_ms,
        }


# Global config instance
KAFKA_CONFIG = KafkaConfig()
