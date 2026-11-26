# ============================================================
# AtmoSync – Simulator Configuration
# ============================================================
# This file defines sensor thresholds, container profiles,
# commodity types, and market routes used by the simulator.
# ============================================================

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import os

# -------------------------------------------------------
# SENSOR THRESHOLDS
# -------------------------------------------------------
# These define the "safe zone" for each sensor type.
# Readings outside these ranges trigger anomaly detection.
# -------------------------------------------------------

@dataclass
class SensorThresholds:
    """Safe operating ranges for container sensors."""

    # Temperature (Celsius)
    temp_min: float = 2.0        # Minimum safe temperature
    temp_max: float = 8.0        # Maximum safe temperature
    temp_critical: float = 15.0  # Critical temperature (fast spoilage)

    # Humidity (%)
    humidity_min: float = 85.0   # Minimum safe humidity
    humidity_max: float = 95.0   # Maximum safe humidity
    humidity_critical: float = 70.0  # Critical low (dehydration)

    # Vibration (m/s² – g-force equivalent)
    vibration_normal: float = 0.5    # Normal road vibration
    vibration_warning: float = 1.5   # Warning threshold
    vibration_critical: float = 3.0  # Structural risk


# -------------------------------------------------------
# COMMODITY PROFILES
# -------------------------------------------------------
# Mock commodity data – for demonstration purposes only.
# Prices are illustrative, not real market prices.
# -------------------------------------------------------

@dataclass
class CommodityProfile:
    name: str
    unit: str
    base_price_per_unit: float    # USD
    quantity_per_container: int   # units
    optimal_temp_min: float       # Celsius
    optimal_temp_max: float       # Celsius
    shelf_life_days: float        # At optimal conditions
    spoilage_rate_per_degree: float  # % quality loss per °C/hour above max


COMMODITY_PROFILES: Dict[str, CommodityProfile] = {
    "AVOCADO": CommodityProfile(
        name="Avocado",
        unit="kg",
        base_price_per_unit=2.50,
        quantity_per_container=18000,
        optimal_temp_min=4.0,
        optimal_temp_max=7.0,
        shelf_life_days=21.0,
        spoilage_rate_per_degree=0.015,
    ),
    "STRAWBERRY": CommodityProfile(
        name="Strawberry",
        unit="kg",
        base_price_per_unit=4.80,
        quantity_per_container=12000,
        optimal_temp_min=0.0,
        optimal_temp_max=4.0,
        shelf_life_days=7.0,
        spoilage_rate_per_degree=0.025,
    ),
    "BANANA": CommodityProfile(
        name="Banana",
        unit="kg",
        base_price_per_unit=1.20,
        quantity_per_container=20000,
        optimal_temp_min=13.0,
        optimal_temp_max=15.0,
        shelf_life_days=14.0,
        spoilage_rate_per_degree=0.020,
    ),
    "MANGO": CommodityProfile(
        name="Mango",
        unit="kg",
        base_price_per_unit=3.20,
        quantity_per_container=15000,
        optimal_temp_min=10.0,
        optimal_temp_max=13.0,
        shelf_life_days=18.0,
        spoilage_rate_per_degree=0.018,
    ),
    "TOMATO": CommodityProfile(
        name="Tomato",
        unit="kg",
        base_price_per_unit=1.80,
        quantity_per_container=16000,
        optimal_temp_min=10.0,
        optimal_temp_max=12.0,
        shelf_life_days=10.0,
        spoilage_rate_per_degree=0.022,
    ),
}


# -------------------------------------------------------
# CONTAINER PROFILES
# -------------------------------------------------------
# Each container has an ID, commodity, origin, and
# a destination (original market).
# -------------------------------------------------------

@dataclass
class ContainerProfile:
    container_id: str
    commodity_key: str
    origin: str
    destination: str
    hours_in_transit: float
    total_transit_hours: float


CONTAINER_PROFILES: List[ContainerProfile] = [
    ContainerProfile("CTR-001", "AVOCADO",    "Mexico City",  "New York",    12.0, 72.0),
    ContainerProfile("CTR-002", "STRAWBERRY", "California",   "Chicago",     8.0,  48.0),
    ContainerProfile("CTR-003", "BANANA",     "Ecuador",      "Miami",       36.0, 120.0),
    ContainerProfile("CTR-004", "MANGO",      "Brazil",       "London",      48.0, 168.0),
    ContainerProfile("CTR-005", "TOMATO",     "Florida",      "Boston",      5.0,  36.0),
]


# -------------------------------------------------------
# MARKET ROUTES
# -------------------------------------------------------
# Mock alternative markets and their travel times from
# each container's current estimated position.
# Prices are mock premiums/discounts vs. base price.
# -------------------------------------------------------

@dataclass
class MarketRoute:
    market_name: str
    city: str
    hours_from_current: float    # Estimated travel hours
    price_multiplier: float      # vs. original market base price


ALTERNATIVE_MARKETS: Dict[str, List[MarketRoute]] = {
    "CTR-001": [
        MarketRoute("Philadelphia Hub",  "Philadelphia",  4.0, 0.95),
        MarketRoute("Atlanta Market",    "Atlanta",       8.0, 0.98),
        MarketRoute("Baltimore Fresh",   "Baltimore",     5.5, 0.92),
    ],
    "CTR-002": [
        MarketRoute("Detroit Wholesale", "Detroit",       3.5, 0.97),
        MarketRoute("Indianapolis Hub",  "Indianapolis",  2.0, 0.90),
        MarketRoute("Milwaukee Fresh",   "Milwaukee",     2.5, 0.93),
    ],
    "CTR-003": [
        MarketRoute("Tampa Fresh",       "Tampa",         3.0, 1.02),
        MarketRoute("Atlanta Export",    "Atlanta",       7.0, 0.98),
        MarketRoute("Jacksonville Hub",  "Jacksonville",  2.0, 0.95),
    ],
    "CTR-004": [
        MarketRoute("Amsterdam Fresh",   "Amsterdam",     12.0, 1.05),
        MarketRoute("Rotterdam Port",    "Rotterdam",     10.0, 0.98),
        MarketRoute("Paris Market",      "Paris",         14.0, 1.08),
    ],
    "CTR-005": [
        MarketRoute("Providence Fresh",  "Providence",    1.5, 0.96),
        MarketRoute("Hartford Market",   "Hartford",      2.0, 0.94),
        MarketRoute("New Haven Hub",     "New Haven",     1.8, 0.92),
    ],
}


# -------------------------------------------------------
# ANOMALY INJECTION PROBABILITIES
# -------------------------------------------------------

@dataclass
class AnomalyConfig:
    """Probabilities and parameters for anomaly injection."""
    # Probability per reading that this anomaly occurs
    temp_drift_prob: float = 0.10        # Temperature drift event
    humidity_spike_prob: float = 0.08    # Humidity spike
    vibration_anomaly_prob: float = 0.05 # Vibration anomaly

    # How much anomaly to inject
    temp_drift_max_degrees: float = 8.0
    humidity_spike_max: float = 15.0
    vibration_spike_max: float = 4.0


# -------------------------------------------------------
# SIMULATOR SETTINGS
# -------------------------------------------------------

@dataclass
class SimulatorConfig:
    num_containers: int = int(os.getenv("SIMULATOR_NUM_CONTAINERS", "5"))
    interval_seconds: float = float(os.getenv("SIMULATOR_INTERVAL_SECONDS", "5"))
    anomaly_probability: float = float(os.getenv("SIMULATOR_ANOMALY_PROBABILITY", "0.15"))
    output_to_kafka: bool = True
    output_to_file: bool = True
    output_file: str = "data/sample_data/live_readings.json"
    batch_size: int = 1  # Readings per interval per container


# Global instances for import
SENSOR_THRESHOLDS = SensorThresholds()
ANOMALY_CONFIG = AnomalyConfig()
SIMULATOR_CONFIG = SimulatorConfig()
