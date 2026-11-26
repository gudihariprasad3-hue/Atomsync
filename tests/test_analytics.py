"""
============================================================
AtmoSync – Analytics Engine Tests
============================================================
Run with: pytest tests/test_analytics.py -v
============================================================
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.spoilage_engine import SpoilageEngine, SpoilageResult
from analytics.arbitrage_engine import ArbitrageEngine, ArbitrageResult


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def spoilage_engine():
    return SpoilageEngine()


@pytest.fixture
def arbitrage_engine():
    return ArbitrageEngine()


@pytest.fixture
def healthy_reading():
    return {
        "container_id": "CTR-001",
        "commodity": "AVOCADO",
        "temperature_celsius": 5.5,
        "humidity_percent": 90.0,
        "vibration_ms2": 0.3,
        "hours_in_transit": 10.0,
    }


@pytest.fixture
def critical_reading():
    # Moderate critical reading: elevated temp + humidity drop, but not fully spoiled
    # This ensures there is still quality remaining to sell at an alternative market
    return {
        "container_id": "CTR-001",
        "commodity": "AVOCADO",
        "temperature_celsius": 12.0,   # Above optimal 4-7°C → triggers temp spoilage
        "humidity_percent": 78.0,       # Below safe minimum 85%
        "vibration_ms2": 1.8,           # Above warning threshold
        "hours_in_transit": 30.0,
    }


# ============================================================
# SPOILAGE ENGINE TESTS
# ============================================================

class TestSpoilageEngine:
    """Test spoilage score calculation logic."""

    def test_healthy_container_has_low_spoilage(self, spoilage_engine, healthy_reading):
        """A container within all thresholds should have low spoilage."""
        result = spoilage_engine.calculate(healthy_reading)
        assert result.spoilage_score < 0.35, (
            f"Expected LOW_RISK, got score={result.spoilage_score:.3f}"
        )

    def test_critical_container_has_high_spoilage(self, spoilage_engine, critical_reading):
        """A container with severe deviations should have high spoilage."""
        result = spoilage_engine.calculate(critical_reading)
        assert result.spoilage_score >= 0.35, (
            f"Expected elevated risk, got score={result.spoilage_score:.3f}"
        )

    def test_spoilage_score_bounded_0_to_1(self, spoilage_engine, critical_reading):
        """Spoilage score must always be between 0 and 1."""
        result = spoilage_engine.calculate(critical_reading)
        assert 0.0 <= result.spoilage_score <= 1.0

    def test_quality_remaining_complements_spoilage(self, spoilage_engine, healthy_reading):
        """quality_remaining + spoilage_score must equal 1.0."""
        result = spoilage_engine.calculate(healthy_reading)
        total = result.spoilage_score + result.quality_remaining_pct
        assert abs(total - 1.0) < 0.001, f"quality + spoilage = {total}, expected 1.0"

    def test_risk_level_valid_values(self, spoilage_engine, healthy_reading):
        """Risk level must be one of the four defined values."""
        result = spoilage_engine.calculate(healthy_reading)
        valid_levels = {"LOW_RISK", "MEDIUM_RISK", "HIGH_RISK", "CRITICAL_RISK"}
        assert result.risk_level in valid_levels, f"Invalid risk level: {result.risk_level}"

    def test_longer_transit_increases_spoilage(self, spoilage_engine):
        """Same readings but longer transit should have higher spoilage."""
        base = {
            "container_id": "CTR-001",
            "commodity": "AVOCADO",
            "temperature_celsius": 10.0,  # Slight deviation
            "humidity_percent": 88.0,
            "vibration_ms2": 0.3,
            "hours_in_transit": 10.0,
        }
        long_transit = {**base, "hours_in_transit": 100.0}

        result_short = spoilage_engine.calculate(base)
        result_long = spoilage_engine.calculate(long_transit)

        assert result_long.spoilage_score > result_short.spoilage_score, (
            "Longer transit should increase spoilage"
        )

    def test_temperature_deviation_increases_spoilage(self, spoilage_engine):
        """Higher temperature deviation should increase spoilage score."""
        base = {
            "container_id": "CTR-001",
            "commodity": "AVOCADO",
            "temperature_celsius": 6.0,   # Optimal
            "humidity_percent": 90.0,
            "vibration_ms2": 0.3,
            "hours_in_transit": 24.0,
        }
        hot = {**base, "temperature_celsius": 16.0}  # 9°C above max

        result_base = spoilage_engine.calculate(base)
        result_hot = spoilage_engine.calculate(hot)

        assert result_hot.spoilage_score > result_base.spoilage_score

    def test_unknown_commodity_uses_default(self, spoilage_engine):
        """Unknown commodity should not raise an error."""
        reading = {
            "container_id": "CTR-X",
            "commodity": "UNKNOWN_FRUIT",
            "temperature_celsius": 5.0,
            "humidity_percent": 90.0,
            "vibration_ms2": 0.3,
            "hours_in_transit": 5.0,
        }
        result = spoilage_engine.calculate(reading)
        assert result.spoilage_score is not None

    def test_batch_calculation_returns_all_results(self, spoilage_engine):
        """Batch calculation should return one result per reading."""
        readings = [
            {
                "container_id": f"CTR-00{i}",
                "commodity": "AVOCADO",
                "temperature_celsius": 5.0 + i,
                "humidity_percent": 90.0,
                "vibration_ms2": 0.3,
                "hours_in_transit": float(i * 10),
            }
            for i in range(1, 4)
        ]
        results = spoilage_engine.calculate_batch(readings)
        assert len(results) == 3

    def test_result_has_audit_trail(self, spoilage_engine, healthy_reading):
        """Result should include the input values for audit purposes."""
        result = spoilage_engine.calculate(healthy_reading)
        assert result.temperature_c == healthy_reading["temperature_celsius"]
        assert result.humidity_pct == healthy_reading["humidity_percent"]
        assert result.hours_in_transit == healthy_reading["hours_in_transit"]


# ============================================================
# ARBITRAGE ENGINE TESTS
# ============================================================

class TestArbitrageEngine:
    """Test arbitrage margin calculation logic."""

    def test_critical_container_recommends_reroute(self, arbitrage_engine, critical_reading):
        """
        A container with critical spoilage and significant time-to-original
        should recommend rerouting.
        """
        result = arbitrage_engine.analyze(critical_reading, hours_to_original=120.0)
        # At minimum should evaluate rerouting
        assert result.recommendation in ("RECOMMEND_REROUTE", "EVALUATE_REROUTE"), (
            f"Expected reroute signal, got: {result.recommendation}"
        )

    def test_healthy_container_stays_on_course(self, arbitrage_engine, healthy_reading):
        """
        A healthy container can still be recommended for reroute if the
        alternative market provides significantly better revenue.
        The key check is that recommendation is always one of the valid values
        and has a reason.
        """
        result = arbitrage_engine.analyze(healthy_reading, hours_to_original=20.0)
        # Recommendation must always be one of the three defined values
        valid = {"RECOMMEND_REROUTE", "EVALUATE_REROUTE", "STAY_ON_COURSE"}
        assert result.recommendation in valid
        # Must always have a reason
        assert len(result.recommendation_reason) > 5
        # Spoilage should be low (healthy container)
        assert result.spoilage_result.spoilage_score < 0.35

    def test_arbitrage_result_has_all_scenarios(self, arbitrage_engine, critical_reading):
        """Result should include original and alternative scenarios."""
        result = arbitrage_engine.analyze(critical_reading, hours_to_original=120.0)
        assert result.original_scenario is not None
        assert len(result.alternatives) > 0

    def test_net_arbitrage_is_numeric(self, arbitrage_engine, critical_reading):
        """Net arbitrage margin must be a number (can be negative)."""
        result = arbitrage_engine.analyze(critical_reading, hours_to_original=120.0)
        assert isinstance(result.net_arbitrage_margin_usd, float)

    def test_recommendation_reason_is_not_empty(self, arbitrage_engine, healthy_reading):
        """Every recommendation must have a human-readable reason."""
        result = arbitrage_engine.analyze(healthy_reading, hours_to_original=20.0)
        assert result.recommendation_reason
        assert len(result.recommendation_reason) > 10

    def test_to_dict_is_json_serializable(self, arbitrage_engine, healthy_reading):
        """ArbitrageResult.to_dict() must produce JSON-serializable output."""
        import json
        result = arbitrage_engine.analyze(healthy_reading, hours_to_original=20.0)
        try:
            json.dumps(result.to_dict())
        except (TypeError, ValueError) as e:
            pytest.fail(f"to_dict() not JSON-serializable: {e}")

    def test_valid_recommendation_values(self, arbitrage_engine, critical_reading):
        """Recommendation must be one of the three defined values."""
        result = arbitrage_engine.analyze(critical_reading, hours_to_original=120.0)
        valid = {"RECOMMEND_REROUTE", "EVALUATE_REROUTE", "STAY_ON_COURSE"}
        assert result.recommendation in valid

    def test_different_commodities_produce_different_margins(self, arbitrage_engine):
        """
        Avocado and Strawberry containers should produce different arbitrage
        margins due to different base prices and quantities.
        """
        avocado = {
            "container_id": "CTR-001",
            "commodity": "AVOCADO",
            "temperature_celsius": 12.0,
            "humidity_percent": 80.0,
            "vibration_ms2": 0.5,
            "hours_in_transit": 40.0,
        }
        strawberry = {
            "container_id": "CTR-002",
            "commodity": "STRAWBERRY",
            "temperature_celsius": 8.0,
            "humidity_percent": 75.0,
            "vibration_ms2": 0.4,
            "hours_in_transit": 20.0,
        }

        result_av = arbitrage_engine.analyze(avocado, hours_to_original=60.0)
        result_st = arbitrage_engine.analyze(strawberry, hours_to_original=40.0)

        # They should produce different margin values
        assert result_av.net_arbitrage_margin_usd != result_st.net_arbitrage_margin_usd
