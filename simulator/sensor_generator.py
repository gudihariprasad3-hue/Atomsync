"""
============================================================
AtmoSync – Python IoT Sensor Simulator (Module A)
============================================================

WHAT THIS MODULE DOES:
    Simulates IoT sensor telemetry from agricultural
    shipping containers. Each "container" tracks:
      - Temperature (°C)
      - Humidity (%)
      - Vibration (m/s²)

WHY IT EXISTS:
    In a real system, physical IoT sensors inside each
    container would transmit this data via MQTT or HTTP.
    This simulator generates realistic (and sometimes
    abnormal) readings so we can build and test the
    entire pipeline without physical hardware.

HOW TO RUN:
    python simulator/sensor_generator.py

    This will print JSON readings to the console and also
    write them to data/sample_data/live_readings.json
============================================================
"""

import json
import random
import time
import uuid
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path

# Add parent directory to path so we can import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.config import (
    CONTAINER_PROFILES,
    COMMODITY_PROFILES,
    SENSOR_THRESHOLDS,
    ANOMALY_CONFIG,
    SIMULATOR_CONFIG,
    ContainerProfile,
)


# ============================================================
# SENSOR READING DATA MODEL
# ============================================================

def create_sensor_reading(
    container_id: str,
    temperature: float,
    humidity: float,
    vibration: float,
    commodity: str,
    origin: str,
    destination: str,
    hours_in_transit: float,
    condition: str,
    anomalies: list,
) -> Dict[str, Any]:
    """
    Creates a validated sensor reading dictionary.

    This is the core data structure that flows through
    the entire AtmoSync pipeline.
    """
    reading = {
        # Identification
        "event_id": str(uuid.uuid4()),
        "container_id": container_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),

        # Sensor readings (rounded to 2 decimal places)
        "temperature_celsius": round(temperature, 2),
        "humidity_percent": round(humidity, 2),
        "vibration_ms2": round(vibration, 3),

        # Container context
        "commodity": commodity,
        "origin": origin,
        "destination": destination,
        "hours_in_transit": round(hours_in_transit, 1),

        # Condition classification
        "condition": condition,       # NORMAL, WARNING, CRITICAL
        "anomalies": anomalies,       # List of active anomaly types

        # Thresholds (for downstream validation)
        "thresholds": {
            "temp_min": SENSOR_THRESHOLDS.temp_min,
            "temp_max": SENSOR_THRESHOLDS.temp_max,
            "humidity_min": SENSOR_THRESHOLDS.humidity_min,
            "humidity_max": SENSOR_THRESHOLDS.humidity_max,
            "vibration_warning": SENSOR_THRESHOLDS.vibration_warning,
        },
    }

    # Validate the reading before returning
    _validate_reading(reading)
    return reading


def _validate_reading(reading: Dict[str, Any]) -> None:
    """
    Basic validation on a sensor reading.
    Raises ValueError if any field is out of physically
    possible range (not just safe range).
    """
    temp = reading["temperature_celsius"]
    hum = reading["humidity_percent"]
    vib = reading["vibration_ms2"]

    if not (-30.0 <= temp <= 60.0):
        raise ValueError(f"Temperature {temp}°C is physically impossible")
    if not (0.0 <= hum <= 100.0):
        raise ValueError(f"Humidity {hum}% is out of range 0-100")
    if not (0.0 <= vib <= 20.0):
        raise ValueError(f"Vibration {vib} m/s² is out of physical range")
    if not reading["container_id"]:
        raise ValueError("Container ID cannot be empty")
    if not reading["event_id"]:
        raise ValueError("Event ID cannot be empty")


# ============================================================
# CONTAINER STATE TRACKER
# ============================================================

class ContainerState:
    """
    Maintains the current internal state of a simulated
    container so readings change gradually and realistically
    rather than jumping randomly each time.

    This models "sensor inertia" – temperature doesn't
    jump from 6°C to 15°C instantly; it drifts.
    """

    def __init__(self, profile: ContainerProfile):
        self.profile = profile
        commodity = COMMODITY_PROFILES[profile.commodity_key]

        # Start near the optimal midpoint for the commodity
        self.temperature = (commodity.optimal_temp_min + commodity.optimal_temp_max) / 2
        self.humidity = (SENSOR_THRESHOLDS.humidity_min + SENSOR_THRESHOLDS.humidity_max) / 2
        self.vibration = random.uniform(0.1, 0.4)
        self.hours_in_transit = profile.hours_in_transit

        # Drift tracking (simulates gradual sensor changes)
        self._temp_drift_active = False
        self._temp_drift_rate = 0.0        # °C per reading
        self._humidity_spike_active = False
        self._vibration_anomaly_active = False

    def update(self) -> Dict[str, Any]:
        """
        Advances the container state by one reading interval.
        Applies gradual drift, random anomalies, and returns
        the full sensor reading dictionary.
        """
        anomalies = []
        self.hours_in_transit += (SIMULATOR_CONFIG.interval_seconds / 3600.0)

        # -- Temperature --
        self._update_temperature(anomalies)

        # -- Humidity --
        self._update_humidity(anomalies)

        # -- Vibration --
        self._update_vibration(anomalies)

        # Determine overall condition
        condition = self._classify_condition()

        return create_sensor_reading(
            container_id=self.profile.container_id,
            temperature=self.temperature,
            humidity=self.humidity,
            vibration=self.vibration,
            commodity=self.profile.commodity_key,
            origin=self.profile.origin,
            destination=self.profile.destination,
            hours_in_transit=self.hours_in_transit,
            condition=condition,
            anomalies=anomalies,
        )

    def _update_temperature(self, anomalies: list) -> None:
        """Update temperature with realistic drift and anomaly injection."""
        commodity = COMMODITY_PROFILES[self.profile.commodity_key]
        optimal_mid = (commodity.optimal_temp_min + commodity.optimal_temp_max) / 2

        # Inject temperature drift anomaly
        if not self._temp_drift_active:
            if random.random() < ANOMALY_CONFIG.temp_drift_prob:
                # Start a drift event
                self._temp_drift_active = True
                drift_direction = random.choice([1, -1])
                self._temp_drift_rate = drift_direction * random.uniform(0.05, 0.3)

        # Natural mean-reversion (slight pull back to optimal)
        reversion = (optimal_mid - self.temperature) * 0.02

        if self._temp_drift_active:
            self.temperature += self._temp_drift_rate + reversion
            anomalies.append("TEMPERATURE_DRIFT")
            # Stop drift after it reaches critical or randomly
            if (self.temperature > SENSOR_THRESHOLDS.temp_critical or
                    self.temperature < -5.0 or
                    random.random() < 0.08):
                self._temp_drift_active = False
                self._temp_drift_rate = 0.0
        else:
            # Normal micro-fluctuation
            self.temperature += reversion + random.uniform(-0.1, 0.1)

        # Clamp to physically realistic range
        self.temperature = max(-10.0, min(30.0, self.temperature))

    def _update_humidity(self, anomalies: list) -> None:
        """Update humidity with spike events."""
        optimal_mid = (SENSOR_THRESHOLDS.humidity_min + SENSOR_THRESHOLDS.humidity_max) / 2

        if not self._humidity_spike_active:
            if random.random() < ANOMALY_CONFIG.humidity_spike_prob:
                self._humidity_spike_active = True

        if self._humidity_spike_active:
            # Spike direction: usually a drop (door opened, refrigeration issue)
            self.humidity += random.uniform(-2.0, 0.5)
            anomalies.append("HUMIDITY_ANOMALY")
            if random.random() < 0.15:
                self._humidity_spike_active = False
        else:
            # Normal reversion toward optimal
            reversion = (optimal_mid - self.humidity) * 0.03
            self.humidity += reversion + random.uniform(-0.3, 0.3)

        self.humidity = max(40.0, min(100.0, self.humidity))

    def _update_vibration(self, anomalies: list) -> None:
        """Update vibration with road/handling anomalies."""
        if not self._vibration_anomaly_active:
            if random.random() < ANOMALY_CONFIG.vibration_anomaly_prob:
                self._vibration_anomaly_active = True

        if self._vibration_anomaly_active:
            self.vibration = random.uniform(
                SENSOR_THRESHOLDS.vibration_warning,
                ANOMALY_CONFIG.vibration_spike_max,
            )
            anomalies.append("VIBRATION_ANOMALY")
            if random.random() < 0.25:
                self._vibration_anomaly_active = False
        else:
            # Normal road vibration with micro-fluctuation
            self.vibration = random.uniform(0.05, SENSOR_THRESHOLDS.vibration_normal)

    def _classify_condition(self) -> str:
        """
        Classify overall container condition based on
        all sensor readings.
        """
        commodity = COMMODITY_PROFILES[self.profile.commodity_key]

        temp_over = self.temperature - commodity.optimal_temp_max
        temp_under = commodity.optimal_temp_min - self.temperature
        temp_deviation = max(temp_over, temp_under, 0)

        if (temp_deviation > 5.0 or
                self.humidity < 60.0 or
                self.vibration > SENSOR_THRESHOLDS.vibration_critical):
            return "CRITICAL"

        if (temp_deviation > 2.0 or
                self.humidity < SENSOR_THRESHOLDS.humidity_min or
                self.vibration > SENSOR_THRESHOLDS.vibration_warning):
            return "WARNING"

        return "NORMAL"


# ============================================================
# SIMULATOR ENGINE
# ============================================================

class SensorSimulator:
    """
    Main simulator engine. Manages multiple container
    state objects and generates readings on a schedule.
    """

    def __init__(self):
        # Create state tracker for each configured container
        self.containers: Dict[str, ContainerState] = {}
        for profile in CONTAINER_PROFILES:
            self.containers[profile.container_id] = ContainerState(profile)

        # Prepare output file
        output_path = Path(SIMULATOR_CONFIG.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_file = output_path
        self.readings_count = 0

        # Optional Kafka producer (imported lazily to avoid dependency errors)
        self._kafka_producer = None

    def _get_kafka_producer(self):
        """Lazily load Kafka producer to avoid startup errors."""
        if self._kafka_producer is None:
            try:
                from kafka.producer_client import AtmoSyncProducer
                self._kafka_producer = AtmoSyncProducer()
                print("[SIMULATOR] Kafka producer connected.")
            except Exception as e:
                print(f"[SIMULATOR] Kafka not available ({e}). Running in file-only mode.")
        return self._kafka_producer

    def generate_reading(self, container_id: str) -> Dict[str, Any]:
        """Generate a single reading for one container."""
        return self.containers[container_id].update()

    def generate_all_readings(self) -> list:
        """Generate readings for all containers."""
        return [
            self.containers[cid].update()
            for cid in self.containers
        ]

    def run(self, max_iterations: Optional[int] = None):
        """
        Main simulation loop.

        Args:
            max_iterations: Stop after this many cycles.
                           None = run forever (Ctrl+C to stop).
        """
        print("=" * 60)
        print("AtmoSync IoT Sensor Simulator")
        print("=" * 60)
        print(f"Containers:       {len(self.containers)}")
        print(f"Interval:         {SIMULATOR_CONFIG.interval_seconds}s")
        print(f"Output file:      {self.output_file}")
        print(f"Kafka output:     {SIMULATOR_CONFIG.output_to_kafka}")
        print("Press Ctrl+C to stop.\n")

        iteration = 0
        try:
            while True:
                iteration += 1
                readings = self.generate_all_readings()
                self.readings_count += len(readings)

                for reading in readings:
                    # Print to console
                    self._print_reading(reading)

                    # Write to file
                    if SIMULATOR_CONFIG.output_to_file:
                        with open(self.output_file, "a") as f:
                            f.write(json.dumps(reading) + "\n")

                    # Send to Kafka
                    if SIMULATOR_CONFIG.output_to_kafka:
                        producer = self._get_kafka_producer()
                        if producer:
                            try:
                                producer.send(reading)
                            except Exception as e:
                                print(f"[SIMULATOR] Kafka send failed: {e}")

                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Cycle {iteration} complete. "
                      f"Total readings: {self.readings_count}\n")

                if max_iterations and iteration >= max_iterations:
                    print(f"[SIMULATOR] Completed {max_iterations} cycles. Stopping.")
                    break

                time.sleep(SIMULATOR_CONFIG.interval_seconds)

        except KeyboardInterrupt:
            print(f"\n[SIMULATOR] Stopped by user. Total readings: {self.readings_count}")

    def _print_reading(self, reading: Dict[str, Any]) -> None:
        """Print a formatted reading to the console."""
        condition_symbol = {
            "NORMAL": "[OK]",
            "WARNING": "[WARN]",
            "CRITICAL": "[CRIT]",
        }.get(reading["condition"], "[?]")

        anomaly_str = ", ".join(reading["anomalies"]) if reading["anomalies"] else "None"

        print(
            f"  {condition_symbol} {reading['container_id']:8s} | "
            f"{reading['commodity']:10s} | "
            f"Temp: {reading['temperature_celsius']:6.2f}°C | "
            f"Humid: {reading['humidity_percent']:5.1f}% | "
            f"Vib: {reading['vibration_ms2']:5.3f} m/s² | "
            f"Anomalies: {anomaly_str}"
        )


# ============================================================
# SAMPLE DATA GENERATOR
# ============================================================

def generate_sample_dataset(
    num_readings_per_container: int = 100,
    output_file: str = "data/sample_data/sample_readings.json",
) -> list:
    """
    Generate a fixed sample dataset for testing.
    This is deterministic (same seed = same output).

    Returns a list of all readings.
    """
    random.seed(42)  # Fixed seed for reproducibility

    simulator = SensorSimulator()

    # Override Kafka to file-only
    SIMULATOR_CONFIG.output_to_kafka = False
    SIMULATOR_CONFIG.output_to_file = False

    all_readings = []
    for _ in range(num_readings_per_container):
        readings = simulator.generate_all_readings()
        all_readings.extend(readings)

    # Write to file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for reading in all_readings:
            f.write(json.dumps(reading) + "\n")

    print(f"[SAMPLE DATA] Generated {len(all_readings)} readings -> {output_file}")
    return all_readings


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AtmoSync IoT Sensor Simulator")
    parser.add_argument(
        "--mode",
        choices=["live", "sample"],
        default="live",
        help="'live' = continuous streaming; 'sample' = generate test dataset",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of cycles for live mode (default: infinite)",
    )
    parser.add_argument(
        "--no-kafka",
        action="store_true",
        help="Disable Kafka output (file + console only)",
    )

    args = parser.parse_args()

    if args.no_kafka:
        SIMULATOR_CONFIG.output_to_kafka = False

    if args.mode == "sample":
        generate_sample_dataset()
    else:
        simulator = SensorSimulator()
        simulator.run(max_iterations=args.iterations)
