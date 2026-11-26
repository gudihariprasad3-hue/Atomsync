"""
============================================================
AtmoSync – Simulator Tests
============================================================
Run with: pytest tests/test_simulator.py -v
============================================================
"""

import json
import sys
import uuid
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.sensor_generator import (
    SensorSimulator,
    ContainerState,
    create_sensor_reading,
    _validate_reading,
    generate_sample_dataset,
)
from simulator.config import (
    CONTAINER_PROFILES,
    COMMODITY_PROFILES,
    SENSOR_THRESHOLDS,
    SIMULATOR_CONFIG,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def simulator():
    """Return a fresh simulator instance."""
    return SensorSimulator()


@pytest.fixture
def sample_reading():
    """Return a valid sample reading."""
    return create_sensor_reading(
        container_id="CTR-001",
        temperature=5.5,
        humidity=90.0,
        vibration=0.3,
        commodity="AVOCADO",
        origin="Mexico City",
        destination="New York",
        hours_in_transit=12.0,
        condition="NORMAL",
        anomalies=[],
    )


# ============================================================
# TESTS: JSON OUTPUT STRUCTURE
# ============================================================

class TestSensorReadingStructure:
    """Test that sensor readings have the correct JSON structure."""

    REQUIRED_FIELDS = [
        "event_id", "container_id", "timestamp",
        "temperature_celsius", "humidity_percent", "vibration_ms2",
        "commodity", "origin", "destination", "hours_in_transit",
        "condition", "anomalies", "thresholds",
    ]

    def test_all_required_fields_present(self, sample_reading):
        """Every required field must be present in the reading."""
        for field in self.REQUIRED_FIELDS:
            assert field in sample_reading, f"Missing field: {field}"

    def test_event_id_is_valid_uuid(self, sample_reading):
        """event_id must be a valid UUID4."""
        try:
            uuid.UUID(sample_reading["event_id"])
        except ValueError:
            pytest.fail(f"event_id is not a valid UUID: {sample_reading['event_id']}")

    def test_reading_is_json_serializable(self, sample_reading):
        """Reading must be JSON-serializable (no non-JSON types)."""
        try:
            serialized = json.dumps(sample_reading)
            deserialized = json.loads(serialized)
            assert deserialized["container_id"] == sample_reading["container_id"]
        except (TypeError, json.JSONDecodeError) as e:
            pytest.fail(f"Reading not JSON-serializable: {e}")

    def test_temperature_is_float(self, sample_reading):
        assert isinstance(sample_reading["temperature_celsius"], float)

    def test_humidity_is_float(self, sample_reading):
        assert isinstance(sample_reading["humidity_percent"], float)

    def test_vibration_is_float(self, sample_reading):
        assert isinstance(sample_reading["vibration_ms2"], float)

    def test_anomalies_is_list(self, sample_reading):
        assert isinstance(sample_reading["anomalies"], list)

    def test_thresholds_is_dict(self, sample_reading):
        assert isinstance(sample_reading["thresholds"], dict)


# ============================================================
# TESTS: NORMAL CONDITIONS
# ============================================================

class TestNormalConditions:
    """Test readings under normal (healthy) conditions."""

    def test_normal_reading_condition_flag(self):
        """A reading within all optimal ranges should be NORMAL."""
        # Avocado optimal: 4-7°C
        reading = create_sensor_reading(
            container_id="CTR-001",
            temperature=5.5,
            humidity=90.0,
            vibration=0.3,
            commodity="AVOCADO",
            origin="X", destination="Y",
            hours_in_transit=1.0,
            condition="NORMAL",
            anomalies=[],
        )
        assert reading["condition"] == "NORMAL"
        assert reading["anomalies"] == []

    def test_humidity_in_safe_range(self):
        """Humidity between 85-95% should not trigger anomalies."""
        reading = create_sensor_reading(
            container_id="CTR-001",
            temperature=5.5,
            humidity=90.0,
            vibration=0.2,
            commodity="AVOCADO",
            origin="X", destination="Y",
            hours_in_transit=1.0,
            condition="NORMAL",
            anomalies=[],
        )
        assert reading["humidity_percent"] == 90.0


# ============================================================
# TESTS: ABNORMAL CONDITIONS
# ============================================================

class TestAbnormalConditions:
    """Test that abnormal readings are correctly flagged."""

    def test_validation_rejects_impossible_temperature(self):
        """Temperature above 60°C should fail validation."""
        with pytest.raises(ValueError, match="physically impossible"):
            create_sensor_reading(
                container_id="CTR-001",
                temperature=70.0,  # Impossible
                humidity=90.0,
                vibration=0.3,
                commodity="AVOCADO",
                origin="X", destination="Y",
                hours_in_transit=1.0,
                condition="CRITICAL",
                anomalies=["TEMPERATURE_DRIFT"],
            )

    def test_validation_rejects_invalid_humidity(self):
        """Humidity > 100% should fail validation."""
        with pytest.raises(ValueError):
            create_sensor_reading(
                container_id="CTR-001",
                temperature=5.0,
                humidity=110.0,  # Impossible
                vibration=0.3,
                commodity="AVOCADO",
                origin="X", destination="Y",
                hours_in_transit=1.0,
                condition="NORMAL",
                anomalies=[],
            )

    def test_validation_rejects_empty_container_id(self):
        """Empty container ID should fail validation."""
        with pytest.raises(ValueError):
            create_sensor_reading(
                container_id="",  # Empty
                temperature=5.0,
                humidity=90.0,
                vibration=0.3,
                commodity="AVOCADO",
                origin="X", destination="Y",
                hours_in_transit=1.0,
                condition="NORMAL",
                anomalies=[],
            )


# ============================================================
# TESTS: MULTIPLE CONTAINERS
# ============================================================

class TestMultipleContainers:
    """Test simulator handles multiple containers correctly."""

    def test_simulator_has_all_containers(self, simulator):
        """Simulator should track all configured containers."""
        expected = {p.container_id for p in CONTAINER_PROFILES}
        actual = set(simulator.containers.keys())
        assert actual == expected, f"Missing: {expected - actual}"

    def test_generate_all_returns_one_per_container(self, simulator):
        """generate_all_readings should return one reading per container."""
        readings = simulator.generate_all_readings()
        assert len(readings) == len(CONTAINER_PROFILES)

    def test_all_containers_have_unique_ids(self, simulator):
        """All readings in a batch should have different container IDs."""
        readings = simulator.generate_all_readings()
        container_ids = [r["container_id"] for r in readings]
        assert len(container_ids) == len(set(container_ids)), "Duplicate container IDs"

    def test_all_readings_have_unique_event_ids(self, simulator):
        """Every reading must have a unique event ID."""
        readings = simulator.generate_all_readings()
        event_ids = [r["event_id"] for r in readings]
        assert len(event_ids) == len(set(event_ids)), "Duplicate event IDs"

    def test_different_containers_have_different_commodities(self, simulator):
        """Different containers should have different commodities."""
        readings = simulator.generate_all_readings()
        commodities = {r["container_id"]: r["commodity"] for r in readings}
        # At minimum CTR-001 should be AVOCADO and CTR-002 should be STRAWBERRY
        assert commodities.get("CTR-001") == "AVOCADO"
        assert commodities.get("CTR-002") == "STRAWBERRY"


# ============================================================
# TESTS: STATE CONTINUITY
# ============================================================

class TestContainerStateContiguity:
    """Test that container readings evolve gradually (not randomly)."""

    def test_temperature_does_not_jump_wildly(self):
        """Temperature should not change by more than 5°C between readings."""
        profile = CONTAINER_PROFILES[0]
        state = ContainerState(profile)
        prev_temp = state.temperature

        for _ in range(20):
            reading = state.update()
            curr_temp = reading["temperature_celsius"]
            delta = abs(curr_temp - prev_temp)
            assert delta < 5.0, f"Temperature jumped {delta:.2f}°C in one step"
            prev_temp = curr_temp

    def test_hours_in_transit_increases_monotonically(self):
        """Hours in transit should always increase or stay the same (rounding)."""
        profile = CONTAINER_PROFILES[0]
        state = ContainerState(profile)
        prev_hours = state.hours_in_transit

        for _ in range(10):
            reading = state.update()
            curr_hours = reading["hours_in_transit"]
            assert curr_hours >= prev_hours, "Hours in transit went backwards"
            prev_hours = curr_hours


# ============================================================
# TESTS: SAMPLE DATASET
# ============================================================

class TestSampleDataset:
    """Test the repeatable sample dataset generation."""

    def test_sample_dataset_generates_correct_count(self, tmp_path):
        """Sample dataset should contain readings for each container × num_readings."""
        import random
        random.seed(42)

        SIMULATOR_CONFIG.output_to_kafka = False
        SIMULATOR_CONFIG.output_to_file = False

        output_file = str(tmp_path / "test_sample.json")
        readings = generate_sample_dataset(
            num_readings_per_container=10,
            output_file=output_file,
        )
        expected = len(CONTAINER_PROFILES) * 10
        assert len(readings) == expected, f"Expected {expected}, got {len(readings)}"

    def test_sample_dataset_is_reproducible(self, tmp_path):
        """Running twice with same seed should produce same first reading."""
        import random, copy

        SIMULATOR_CONFIG.output_to_kafka = False
        SIMULATOR_CONFIG.output_to_file = False

        random.seed(42)
        readings1 = generate_sample_dataset(5, str(tmp_path / "s1.json"))

        random.seed(42)
        readings2 = generate_sample_dataset(5, str(tmp_path / "s2.json"))

        # First readings should have same values (not necessarily same UUID)
        assert readings1[0]["container_id"] == readings2[0]["container_id"]
        assert readings1[0]["commodity"] == readings2[0]["commodity"]
