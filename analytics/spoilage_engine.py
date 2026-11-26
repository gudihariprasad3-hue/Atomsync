"""
============================================================
AtmoSync – Spoilage Analytics Engine (Module E)
============================================================

WHAT THIS DOES:
    Pure Python implementation of the spoilage degradation
    model. This runs independently of dbt for use in:
      - Real-time Kafka consumer alerts
      - Testing without Snowflake access
      - Local development and experimentation

DISCLAIMER:
    All spoilage calculations in this module use simplified
    mock formulas for demonstration purposes only. They are
    NOT scientifically validated spoilage models and should
    NOT be used for real-world commodity decisions.

HOW TO TEST:
    python analytics/spoilage_engine.py
============================================================
"""

import sys
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.config import COMMODITY_PROFILES, CONTAINER_PROFILES, ALTERNATIVE_MARKETS

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class SpoilageResult:
    """
    Result of a spoilage calculation for a single container
    at a point in time.
    """
    container_id: str
    commodity: str
    hours_in_transit: float

    # Individual spoilage contributions
    base_transit_spoilage: float      # From time alone
    temp_spoilage_contribution: float # From temperature deviation
    humidity_spoilage_contribution: float
    vibration_spoilage_contribution: float

    # Aggregate scores
    spoilage_score: float             # 0.0 (fresh) to 1.0 (spoiled)
    quality_remaining_pct: float      # 1.0 - spoilage_score
    estimated_hours_remaining: float  # Hours until fully spoiled

    # Risk classification
    risk_level: str                   # LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL_RISK

    # Input values used (for auditability)
    temperature_c: float
    humidity_pct: float
    vibration_ms2: float
    temp_deviation_c: float
    humidity_deviation_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_id": self.container_id,
            "commodity": self.commodity,
            "spoilage_score": round(self.spoilage_score, 4),
            "quality_remaining_pct": round(self.quality_remaining_pct, 4),
            "estimated_hours_remaining": round(self.estimated_hours_remaining, 1),
            "risk_level": self.risk_level,
            "contributions": {
                "base_transit": round(self.base_transit_spoilage, 4),
                "temperature": round(self.temp_spoilage_contribution, 4),
                "humidity": round(self.humidity_spoilage_contribution, 4),
                "vibration": round(self.vibration_spoilage_contribution, 4),
            },
            "inputs": {
                "hours_in_transit": self.hours_in_transit,
                "temperature_c": self.temperature_c,
                "humidity_pct": self.humidity_pct,
                "vibration_ms2": self.vibration_ms2,
            },
        }


# ============================================================
# SPOILAGE ENGINE
# ============================================================

class SpoilageEngine:
    """
    Calculates spoilage risk and degradation scores for
    shipping containers based on sensor readings.

    DISCLAIMER: Mock formula for demonstration purposes only.
    Not a real food science model.
    """

    # Spoilage calculation constants
    # These are illustrative only – not scientifically validated
    BASE_SPOILAGE_RATE_PER_HOUR = 0.02        # At optimal conditions
    TEMP_MULTIPLIER_PER_DEGREE_PER_HOUR = 0.015
    HUMIDITY_MULTIPLIER_PER_PCT = 0.008
    VIBRATION_MULTIPLIER_PER_MS2 = 0.05

    # Risk thresholds
    RISK_THRESHOLDS = {
        "CRITICAL_RISK": 0.80,
        "HIGH_RISK":     0.60,
        "MEDIUM_RISK":   0.35,
        "LOW_RISK":      0.0,
    }

    def calculate(
        self,
        reading: Dict[str, Any],
    ) -> SpoilageResult:
        """
        Calculate spoilage score from a sensor reading.

        Args:
            reading: Sensor reading dictionary from the simulator

        Returns:
            SpoilageResult with all calculated metrics
        """
        container_id = reading["container_id"]
        commodity_key = reading.get("commodity", "AVOCADO")
        hours_in_transit = reading.get("hours_in_transit", 0.0)
        temperature_c = reading["temperature_celsius"]
        humidity_pct = reading["humidity_percent"]
        vibration_ms2 = reading["vibration_ms2"]

        # Get commodity profile for optimal ranges
        commodity = COMMODITY_PROFILES.get(commodity_key)
        if not commodity:
            logger.warning(f"Unknown commodity {commodity_key}, using AVOCADO defaults")
            commodity = COMMODITY_PROFILES["AVOCADO"]

        # --- Calculate deviations ---
        temp_max = commodity.optimal_temp_max
        temp_min = commodity.optimal_temp_min

        temp_deviation_c = max(
            temperature_c - temp_max,  # Too hot
            temp_min - temperature_c,  # Too cold
            0.0
        )

        # Humidity deviation: below optimal min is bad
        humidity_min = 85.0  # From sensor thresholds
        humidity_deviation_pct = max(humidity_min - humidity_pct, 0.0)

        # Vibration excess above warning threshold
        vibration_warning = 1.5
        vibration_excess = max(vibration_ms2 - vibration_warning, 0.0)

        # --- MOCK SPOILAGE FORMULA ---
        # Note: These are simplified illustrative formulas only

        # 1. Base transit spoilage (time-based)
        shelf_hours = commodity.shelf_life_days * 24.0
        base_transit = min(hours_in_transit / shelf_hours, 1.0)

        # 2. Temperature contribution
        temp_contribution = min(
            temp_deviation_c * self.TEMP_MULTIPLIER_PER_DEGREE_PER_HOUR * hours_in_transit,
            0.5
        )

        # 3. Humidity contribution
        humidity_contribution = min(
            humidity_deviation_pct * self.HUMIDITY_MULTIPLIER_PER_PCT,
            0.2
        )

        # 4. Vibration contribution
        vibration_contribution = min(
            vibration_excess * self.VIBRATION_MULTIPLIER_PER_MS2,
            0.15
        )

        # Total spoilage score
        spoilage_score = min(
            base_transit + temp_contribution + humidity_contribution + vibration_contribution,
            1.0
        )
        quality_remaining = 1.0 - spoilage_score

        # Estimated hours remaining
        # Remaining fresh time, reduced by temperature effect
        hours_remaining = max(
            shelf_hours - hours_in_transit - (temp_contribution * shelf_hours * 0.5),
            0.0
        )

        # Risk classification
        risk_level = "LOW_RISK"
        for level, threshold in sorted(
            self.RISK_THRESHOLDS.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            if spoilage_score >= threshold:
                risk_level = level
                break

        return SpoilageResult(
            container_id=container_id,
            commodity=commodity_key,
            hours_in_transit=hours_in_transit,
            base_transit_spoilage=base_transit,
            temp_spoilage_contribution=temp_contribution,
            humidity_spoilage_contribution=humidity_contribution,
            vibration_spoilage_contribution=vibration_contribution,
            spoilage_score=spoilage_score,
            quality_remaining_pct=quality_remaining,
            estimated_hours_remaining=hours_remaining,
            risk_level=risk_level,
            temperature_c=temperature_c,
            humidity_pct=humidity_pct,
            vibration_ms2=vibration_ms2,
            temp_deviation_c=temp_deviation_c,
            humidity_deviation_pct=humidity_deviation_pct,
        )

    def calculate_batch(self, readings: List[Dict[str, Any]]) -> List[SpoilageResult]:
        """Calculate spoilage for multiple readings."""
        return [self.calculate(r) for r in readings]

    def is_at_risk(self, result: SpoilageResult, threshold: float = 0.60) -> bool:
        """Returns True if spoilage score exceeds the given threshold."""
        return result.spoilage_score >= threshold


# ============================================================
# STANDALONE TEST / DEMO
# ============================================================

def run_spoilage_demo():
    """
    Demonstrate the spoilage engine with sample scenarios.
    """
    engine = SpoilageEngine()

    print("=" * 70)
    print("AtmoSync Spoilage Engine – Scenario Demonstration")
    print("=" * 70)
    print("DISCLAIMER: Mock calculations for demonstration only.\n")

    scenarios = [
        {
            "name": "Healthy avocado container (early transit)",
            "reading": {
                "container_id": "CTR-001",
                "commodity": "AVOCADO",
                "temperature_celsius": 5.5,
                "humidity_percent": 92.0,
                "vibration_ms2": 0.3,
                "hours_in_transit": 12.0,
            }
        },
        {
            "name": "Temperature drift – avocado at risk",
            "reading": {
                "container_id": "CTR-001",
                "commodity": "AVOCADO",
                "temperature_celsius": 14.0,  # Well above optimal 4-7°C
                "humidity_percent": 88.0,
                "vibration_ms2": 0.4,
                "hours_in_transit": 48.0,
            }
        },
        {
            "name": "Strawberry – humidity crisis",
            "reading": {
                "container_id": "CTR-002",
                "commodity": "STRAWBERRY",
                "temperature_celsius": 2.0,
                "humidity_percent": 65.0,   # Far below optimal 85-95%
                "vibration_ms2": 0.5,
                "hours_in_transit": 20.0,
            }
        },
        {
            "name": "Mango – critical combined stressors",
            "reading": {
                "container_id": "CTR-004",
                "commodity": "MANGO",
                "temperature_celsius": 20.0,  # Way above optimal 10-13°C
                "humidity_percent": 70.0,
                "vibration_ms2": 2.5,          # High vibration
                "hours_in_transit": 100.0,
            }
        },
    ]

    for scenario in scenarios:
        print(f"\n[SCENARIO] {scenario['name']}")
        print("-" * 50)
        result = engine.calculate(scenario["reading"])

        bar_length = 30
        filled = int(result.spoilage_score * bar_length)
        bar = "#" * filled + "." * (bar_length - filled)

        print(f"  Container:  {result.container_id}")
        print(f"  Commodity:  {result.commodity}")
        print(f"  Transit:    {result.hours_in_transit:.0f}h elapsed")
        print(f"  Spoilage:   [{bar}] {result.spoilage_score*100:.1f}%")
        print(f"  Quality:    {result.quality_remaining_pct*100:.1f}% remaining")
        print(f"  Est. time:  {result.estimated_hours_remaining:.1f}h remaining")
        print(f"  Risk level: {result.risk_level}")
        print(f"  Contributions:")
        print(f"    Base transit:   {result.base_transit_spoilage*100:.2f}%")
        print(f"    Temperature:    {result.temp_spoilage_contribution*100:.2f}%")
        print(f"    Humidity:       {result.humidity_spoilage_contribution*100:.2f}%")
        print(f"    Vibration:      {result.vibration_spoilage_contribution*100:.2f}%")

    print("\n" + "=" * 70)
    print("Demo complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_spoilage_demo()
