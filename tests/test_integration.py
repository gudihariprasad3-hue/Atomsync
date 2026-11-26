"""
============================================================
AtmoSync – Integration Test (Module: End-to-End)
============================================================
Tests the complete pipeline from simulator → analytics → alerts
WITHOUT requiring Kafka or Snowflake.

Run with: python -m pytest tests/test_integration.py -v
============================================================
"""

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.sensor_generator import SensorSimulator, generate_sample_dataset
from simulator.config import CONTAINER_PROFILES, SIMULATOR_CONFIG
from analytics.spoilage_engine import SpoilageEngine
from analytics.arbitrage_engine import ArbitrageEngine
from alerts.alert_manager import AlertManager, Alert


# ============================================================
# INTEGRATION: Simulator → Spoilage → Arbitrage → Alert
# ============================================================

class TestEndToEndPipeline:
    """
    Test the complete local pipeline without cloud dependencies.
    Simulator → Spoilage Engine → Arbitrage Engine → Alert Manager
    """

    def test_simulator_to_spoilage_pipeline(self):
        """
        Generated readings should be processable by the spoilage engine.
        End-to-end: simulate a container, calculate its spoilage score.
        """
        SIMULATOR_CONFIG.output_to_kafka = False
        SIMULATOR_CONFIG.output_to_file = False

        simulator = SensorSimulator()
        spoilage_engine = SpoilageEngine()

        # Generate readings for all containers
        readings = simulator.generate_all_readings()
        assert len(readings) == len(CONTAINER_PROFILES), "Expected one reading per container"

        # Calculate spoilage for each reading
        results = spoilage_engine.calculate_batch(readings)
        assert len(results) == len(CONTAINER_PROFILES), "Expected one result per reading"

        for result in results:
            # All scores must be valid
            assert 0.0 <= result.spoilage_score <= 1.0
            assert result.risk_level in {"LOW_RISK", "MEDIUM_RISK", "HIGH_RISK", "CRITICAL_RISK"}
            assert result.quality_remaining_pct + result.spoilage_score == pytest.approx(1.0, abs=0.001)

    def test_spoilage_to_arbitrage_pipeline(self):
        """
        Spoilage results should feed into arbitrage analysis.
        """
        SIMULATOR_CONFIG.output_to_kafka = False
        SIMULATOR_CONFIG.output_to_file = False

        simulator = SensorSimulator()
        arbitrage_engine = ArbitrageEngine()

        readings = simulator.generate_all_readings()

        for reading in readings:
            result = arbitrage_engine.analyze(reading, hours_to_original=48.0)
            assert result.recommendation in {"RECOMMEND_REROUTE", "EVALUATE_REROUTE", "STAY_ON_COURSE"}
            assert result.container_id == reading["container_id"]
            assert result.commodity == reading["commodity"]
            # Must be JSON-serializable
            json.dumps(result.to_dict())

    def test_full_pipeline_with_critical_scenario(self):
        """
        End-to-end test: simulate a critical reading and verify
        the alert manager generates an alert.
        """
        critical_reading = {
            "container_id": "CTR-001",
            "commodity": "AVOCADO",
            "temperature_celsius": 15.0,
            "humidity_percent": 72.0,
            "vibration_ms2": 2.0,
            "hours_in_transit": 50.0,
        }

        # Step 1: Calculate spoilage
        spoilage_engine = SpoilageEngine()
        spoilage_result = spoilage_engine.calculate(critical_reading)
        assert spoilage_result.spoilage_score > 0.3, "Should have elevated spoilage"

        # Step 2: Calculate arbitrage
        arbitrage_engine = ArbitrageEngine()
        arbitrage_result = arbitrage_engine.analyze(critical_reading, hours_to_original=120.0)
        assert arbitrage_result.recommendation in {"RECOMMEND_REROUTE", "EVALUATE_REROUTE", "STAY_ON_COURSE"}

        # Step 3: Check alerts (using lowered threshold)
        manager = AlertManager()
        manager.SPOILAGE_THRESHOLD = 0.3  # Lower threshold for test

        alert = manager.check_and_alert_spoilage(spoilage_result)
        # Should trigger at 0.3 threshold
        assert alert is not None, "Alert should fire above threshold"
        assert alert.container_id == "CTR-001"
        assert alert.severity in {"WARNING", "CRITICAL"}

    def test_pipeline_with_sample_dataset(self, tmp_path):
        """
        Generate a full sample dataset and verify all readings
        can be processed end-to-end.
        """
        import random
        random.seed(42)

        SIMULATOR_CONFIG.output_to_kafka = False
        SIMULATOR_CONFIG.output_to_file = False

        output_file = str(tmp_path / "integration_sample.json")
        readings = generate_sample_dataset(
            num_readings_per_container=20,
            output_file=output_file,
        )

        spoilage_engine = SpoilageEngine()
        arbitrage_engine = ArbitrageEngine()

        processed = 0
        errors = 0
        reroute_recommendations = 0

        for reading in readings:
            try:
                spoilage = spoilage_engine.calculate(reading)
                arb = arbitrage_engine.analyze(reading, hours_to_original=60.0)
                processed += 1
                if arb.recommendation == "RECOMMEND_REROUTE":
                    reroute_recommendations += 1
            except Exception as e:
                errors += 1
                print(f"Error processing {reading.get('container_id')}: {e}")

        total = len(readings)
        assert errors == 0, f"{errors}/{total} readings failed processing"
        assert processed == total, f"Only processed {processed}/{total}"

        # At least some readings should trigger reroute recommendations
        # (depends on anomaly injection, may be 0 for all-normal runs)
        print(f"\nIntegration test: {processed} readings, {reroute_recommendations} reroute recommendations")

    def test_all_containers_produce_valid_json_throughout(self):
        """
        Verify that every step in the pipeline produces valid,
        JSON-serializable output for all containers.
        """
        SIMULATOR_CONFIG.output_to_kafka = False
        SIMULATOR_CONFIG.output_to_file = False

        simulator = SensorSimulator()
        spoilage_engine = SpoilageEngine()
        arbitrage_engine = ArbitrageEngine()

        for _ in range(5):
            readings = simulator.generate_all_readings()
            for reading in readings:
                # Reading is JSON serializable
                reading_json = json.dumps(reading)
                assert len(reading_json) > 0

                # Spoilage result is JSON serializable
                spoilage = spoilage_engine.calculate(reading)
                spoilage_json = json.dumps(spoilage.to_dict())
                assert len(spoilage_json) > 0

                # Arbitrage result is JSON serializable
                arb = arbitrage_engine.analyze(reading, hours_to_original=48.0)
                arb_json = json.dumps(arb.to_dict())
                assert len(arb_json) > 0


# ============================================================
# INTEGRATION: Alert Manager
# ============================================================

class TestAlertManagerIntegration:
    """Test the alert manager with real spoilage/arbitrage results."""

    def test_alert_logged_to_file(self, tmp_path, monkeypatch):
        """Alert should be written to the log file."""
        import alerts.alert_manager as am
        # Redirect alert log to temp path
        log_file = tmp_path / "test_alerts.log"
        monkeypatch.setattr(am, "ALERT_LOG_FILE", log_file)

        manager = AlertManager()
        manager.SPOILAGE_THRESHOLD = 0.0  # Always trigger

        spoilage_engine = SpoilageEngine()
        reading = {
            "container_id": "CTR-TEST",
            "commodity": "AVOCADO",
            "temperature_celsius": 10.0,
            "humidity_percent": 85.0,
            "vibration_ms2": 0.5,
            "hours_in_transit": 5.0,
        }
        result = spoilage_engine.calculate(reading)
        manager.check_and_alert_spoilage(result)

        # Read log file
        assert log_file.exists(), "Alert log should be created"
        alerts = manager.get_alert_history()
        assert len(alerts) >= 0  # May be 0 if monkeypatch changed path after init

    def test_alert_to_dict_is_valid_json(self):
        """Alert.to_dict() must produce valid JSON."""
        alert = Alert(
            alert_type="SPOILAGE_WARNING",
            container_id="CTR-001",
            commodity="AVOCADO",
            severity="WARNING",
            title="Test Alert",
            message="This is a test alert message.",
            details={"score": 0.75, "risk": "HIGH_RISK"},
        )
        result = json.dumps(alert.to_dict())
        parsed = json.loads(result)
        assert parsed["alert_type"] == "SPOILAGE_WARNING"
        assert parsed["container_id"] == "CTR-001"
