"""
============================================================
AtmoSync – Arbitrage Analytics Engine (Module E)
============================================================

WHAT THIS DOES:
    Calculates the financial value of rerouting a shipping
    container to an alternative market when spoilage risk
    is detected early enough.

DISCLAIMER:
    All prices, calculations and market recommendations in
    this module use mock data for demonstration purposes.
    They are NOT real financial calculations and should NOT
    be used for actual commodity trading decisions.

HOW TO TEST:
    python analytics/arbitrage_engine.py
============================================================
"""

import sys
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from simulator.config import (
    COMMODITY_PROFILES,
    CONTAINER_PROFILES,
    ALTERNATIVE_MARKETS,
    MarketRoute,
)
from analytics.spoilage_engine import SpoilageEngine, SpoilageResult

logger = logging.getLogger(__name__)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class MarketScenario:
    """
    Financial scenario for delivering to one specific market.
    All values are mock/illustrative.
    """
    market_name: str
    city: str
    hours_to_reach: float
    price_per_unit_usd: float    # Mock price per kg
    rerouting_cost_usd: float
    is_original: bool

    # Projected quality when arriving (accounting for extra transit)
    projected_spoilage: float
    projected_quality_pct: float

    # Revenue projection
    gross_revenue_usd: float
    net_revenue_usd: float       # After rerouting cost


@dataclass
class ArbitrageResult:
    """
    Complete arbitrage analysis for a container.
    Contains comparison of original vs best alternative market.
    """
    container_id: str
    commodity: str
    quantity_kg: float
    base_price_usd: float        # Base (original) market price per kg

    spoilage_result: SpoilageResult

    original_scenario: MarketScenario
    alternatives: List[MarketScenario]

    best_alternative: Optional[MarketScenario]
    net_arbitrage_margin_usd: float

    # Decision
    recommendation: str          # RECOMMEND_REROUTE, EVALUATE_REROUTE, STAY_ON_COURSE
    recommendation_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_id": self.container_id,
            "commodity": self.commodity,
            "quantity_kg": self.quantity_kg,
            "spoilage_score": round(self.spoilage_result.spoilage_score, 4),
            "risk_level": self.spoilage_result.risk_level,
            "original_market": {
                "name": self.original_scenario.market_name,
                "city": self.original_scenario.city,
                "hours": self.original_scenario.hours_to_reach,
                "price_per_kg": self.original_scenario.price_per_unit_usd,
                "projected_quality_pct": round(self.original_scenario.projected_quality_pct * 100, 1),
                "net_revenue_usd": round(self.original_scenario.net_revenue_usd, 2),
            },
            "best_alternative": {
                "name": self.best_alternative.market_name if self.best_alternative else None,
                "city": self.best_alternative.city if self.best_alternative else None,
                "hours": self.best_alternative.hours_to_reach if self.best_alternative else None,
                "price_per_kg": self.best_alternative.price_per_unit_usd if self.best_alternative else None,
                "projected_quality_pct": round(self.best_alternative.projected_quality_pct * 100, 1) if self.best_alternative else None,
                "net_revenue_usd": round(self.best_alternative.net_revenue_usd, 2) if self.best_alternative else None,
                "rerouting_cost_usd": round(self.best_alternative.rerouting_cost_usd, 2) if self.best_alternative else None,
            } if self.best_alternative else None,
            "net_arbitrage_margin_usd": round(self.net_arbitrage_margin_usd, 2),
            "recommendation": self.recommendation,
            "recommendation_reason": self.recommendation_reason,
        }


# ============================================================
# ARBITRAGE ENGINE
# ============================================================

class ArbitrageEngine:
    """
    Calculates spoilage arbitrage: the financial difference
    between delivering degraded goods to the original market
    vs. rerouting to a closer alternative.

    DISCLAIMER: Mock formula for demonstration purposes only.
    """

    # Minimum net margin (USD) to recommend rerouting
    MIN_REROUTING_MARGIN = 500.0

    # Additional spoilage rate per transit hour (mock)
    ADDITIONAL_SPOILAGE_RATE = 0.02

    def __init__(self):
        self.spoilage_engine = SpoilageEngine()

    def _project_spoilage_at_arrival(
        self,
        current_spoilage: float,
        hours_to_destination: float,
    ) -> float:
        """
        Project the total spoilage score when the container
        arrives at a given destination.

        Uses a simple compounding mock model:
          additional = hours × rate × (1 + current_spoilage)

        DISCLAIMER: This is a mock projection formula.
        """
        additional = (
            hours_to_destination
            * self.ADDITIONAL_SPOILAGE_RATE
            * (1.0 + current_spoilage)
        )
        return min(current_spoilage + additional, 1.0)

    def _calculate_scenario(
        self,
        commodity_key: str,
        quantity_kg: float,
        current_spoilage: float,
        route: MarketRoute,
        is_original: bool,
    ) -> MarketScenario:
        """Calculate the financial scenario for delivering to one market."""
        commodity = COMMODITY_PROFILES[commodity_key]
        base_price = commodity.base_price_per_unit

        # Apply market price multiplier
        market_price = base_price * route.price_multiplier

        # Project spoilage at arrival
        projected_spoilage = self._project_spoilage_at_arrival(
            current_spoilage,
            route.hours_from_current,
        )
        projected_quality = max(1.0 - projected_spoilage, 0.0)

        # Gross revenue = price × quantity × quality
        gross_revenue = market_price * quantity_kg * projected_quality

        # Rerouting cost (zero for original destination)
        rerouting_cost = 0.0 if is_original else self._estimate_rerouting_cost(route)

        net_revenue = gross_revenue - rerouting_cost

        return MarketScenario(
            market_name=route.market_name,
            city=route.city,
            hours_to_reach=route.hours_from_current,
            price_per_unit_usd=market_price,
            rerouting_cost_usd=rerouting_cost,
            is_original=is_original,
            projected_spoilage=projected_spoilage,
            projected_quality_pct=projected_quality,
            gross_revenue_usd=gross_revenue,
            net_revenue_usd=net_revenue,
        )

    def _estimate_rerouting_cost(self, route: MarketRoute) -> float:
        """
        Estimate rerouting cost for a market.
        Uses hours_from_current as a simple proxy.
        DISCLAIMER: Mock cost model.
        """
        # Base cost + per-hour cost (mock)
        base_cost = 200.0
        per_hour = 50.0
        return base_cost + (route.hours_from_current * per_hour)

    def analyze(
        self,
        reading: Dict[str, Any],
        hours_to_original: float = 60.0,
    ) -> ArbitrageResult:
        """
        Full arbitrage analysis for a sensor reading.

        Args:
            reading: Sensor reading dictionary
            hours_to_original: Hours remaining to reach original destination

        Returns:
            ArbitrageResult with full analysis
        """
        container_id = reading["container_id"]
        commodity_key = reading.get("commodity", "AVOCADO")

        # Get commodity and container info
        commodity = COMMODITY_PROFILES.get(commodity_key, COMMODITY_PROFILES["AVOCADO"])

        # Find the container profile
        container_profile = next(
            (p for p in CONTAINER_PROFILES if p.container_id == container_id),
            CONTAINER_PROFILES[0]
        )
        quantity_kg = commodity.quantity_per_container
        base_price = commodity.base_price_per_unit

        # Step 1: Calculate current spoilage
        spoilage_result = self.spoilage_engine.calculate(reading)

        # Step 2: Get alternative markets for this container
        alternatives_config = ALTERNATIVE_MARKETS.get(container_id, [])

        # Create a mock "original" route
        original_route = MarketRoute(
            market_name=container_profile.destination + " Market",
            city=container_profile.destination,
            hours_from_current=hours_to_original,
            price_multiplier=1.0,
        )

        # Step 3: Calculate scenarios for all markets
        original_scenario = self._calculate_scenario(
            commodity_key, quantity_kg,
            spoilage_result.spoilage_score,
            original_route, is_original=True
        )

        alternative_scenarios = [
            self._calculate_scenario(
                commodity_key, quantity_kg,
                spoilage_result.spoilage_score,
                alt, is_original=False
            )
            for alt in alternatives_config
        ]

        # Step 4: Find best alternative (highest net revenue)
        viable_alternatives = [
            s for s in alternative_scenarios
            if s.hours_to_reach < spoilage_result.estimated_hours_remaining
            and s.projected_quality_pct > 0.2
        ]

        best_alt = None
        if viable_alternatives:
            best_alt = max(viable_alternatives, key=lambda s: s.net_revenue_usd)

        # Step 5: Calculate arbitrage margin
        if best_alt:
            net_margin = best_alt.net_revenue_usd - original_scenario.net_revenue_usd
        else:
            net_margin = 0.0

        # Step 6: Recommendation
        recommendation, reason = self._make_recommendation(
            spoilage_result, best_alt, net_margin,
            spoilage_result.estimated_hours_remaining, hours_to_original
        )

        return ArbitrageResult(
            container_id=container_id,
            commodity=commodity_key,
            quantity_kg=quantity_kg,
            base_price_usd=base_price,
            spoilage_result=spoilage_result,
            original_scenario=original_scenario,
            alternatives=alternative_scenarios,
            best_alternative=best_alt,
            net_arbitrage_margin_usd=net_margin,
            recommendation=recommendation,
            recommendation_reason=reason,
        )

    def _make_recommendation(
        self,
        spoilage: SpoilageResult,
        best_alt: Optional[MarketScenario],
        net_margin: float,
        hours_remaining: float,
        hours_to_original: float,
    ) -> Tuple[str, str]:
        """Determine rerouting recommendation with reason."""

        if best_alt is None:
            return (
                "STAY_ON_COURSE",
                "No viable alternative market identified within estimated shelf life."
            )

        # If the cargo will arrive at zero quality at original market,
        # and the alternative provides positive quality and positive net margin
        if best_alt.projected_quality_pct > 0.1 and best_alt.net_revenue_usd > 0:
            if hours_remaining < hours_to_original or best_alt.net_revenue_usd > net_margin + self.MIN_REROUTING_MARGIN:
                return (
                    "RECOMMEND_REROUTE",
                    f"Cargo will spoil before reaching original destination. "
                    f"Rerouting to {best_alt.market_name} saves "
                    f"${best_alt.net_revenue_usd:,.0f} (mock estimate)."
                )
            elif net_margin > self.MIN_REROUTING_MARGIN:
                return (
                    "RECOMMEND_REROUTE",
                    f"Rerouting to {best_alt.market_name} provides "
                    f"${net_margin:,.0f} arbitrage margin (mock)."
                )

        if hours_remaining < hours_to_original:
            if net_margin > self.MIN_REROUTING_MARGIN:
                return (
                    "RECOMMEND_REROUTE",
                    f"Cargo will spoil before reaching original destination. "
                    f"Rerouting to {best_alt.market_name} saves "
                    f"${net_margin:,.0f} (mock estimate)."
                )
            else:
                return (
                    "EVALUATE_REROUTE",
                    f"Cargo at risk of spoilage. Net margin below threshold "
                    f"(${net_margin:,.0f} vs ${self.MIN_REROUTING_MARGIN:,.0f} min). "
                    f"Evaluate options."
                )

        if spoilage.risk_level in ("HIGH_RISK", "CRITICAL_RISK") and net_margin > self.MIN_REROUTING_MARGIN:
            return (
                "RECOMMEND_REROUTE",
                f"High spoilage risk detected ({spoilage.risk_level}). "
                f"Rerouting to {best_alt.market_name} provides "
                f"${net_margin:,.0f} arbitrage margin (mock)."
            )

        if spoilage.risk_level in ("HIGH_RISK", "CRITICAL_RISK"):
            return (
                "EVALUATE_REROUTE",
                f"High spoilage risk detected. Monitor closely. "
                f"Rerouting margin below threshold."
            )

        return (
            "STAY_ON_COURSE",
            f"Spoilage risk is {spoilage.risk_level}. "
            f"Original route remains optimal."
        )


# ============================================================
# STANDALONE DEMO
# ============================================================

def run_arbitrage_demo():
    """Demonstrate arbitrage calculations with realistic scenarios."""
    engine = ArbitrageEngine()

    print("=" * 70)
    print("AtmoSync Arbitrage Engine – Scenario Analysis")
    print("=" * 70)
    print("DISCLAIMER: All values are mock data for demonstration only.\n")

    scenarios = [
        {
            "name": "[AVO] Avocado – Temperature Drift Emergency",
            "reading": {
                "container_id": "CTR-001",
                "commodity": "AVOCADO",
                "temperature_celsius": 14.5,
                "humidity_percent": 88.0,
                "vibration_ms2": 0.4,
                "hours_in_transit": 48.0,
            },
            "hours_to_original": 60.0,
        },
        {
            "name": "[STRAW] Strawberry – Late Transit, Low Humidity",
            "reading": {
                "container_id": "CTR-002",
                "commodity": "STRAWBERRY",
                "temperature_celsius": 3.0,
                "humidity_percent": 72.0,
                "vibration_ms2": 0.5,
                "hours_in_transit": 35.0,
            },
            "hours_to_original": 40.0,
        },
        {
            "name": "[MANGO] Mango – Critical Combined Failure",
            "reading": {
                "container_id": "CTR-004",
                "commodity": "MANGO",
                "temperature_celsius": 20.0,
                "humidity_percent": 70.0,
                "vibration_ms2": 2.8,
                "hours_in_transit": 100.0,
            },
            "hours_to_original": 120.0,
        },
    ]

    for scenario in scenarios:
        print(f"\n{scenario['name']}")
        print("=" * 65)

        result = engine.analyze(scenario["reading"], scenario["hours_to_original"])
        d = result.to_dict()

        print(f"  Container:         {result.container_id}")
        print(f"  Commodity:         {result.commodity}")
        print(f"  Quantity:          {result.quantity_kg:,} kg")
        print(f"  Spoilage score:    {d['spoilage_score']*100:.1f}%  [{d['risk_level']}]")
        print()
        print(f"  (*) ORIGINAL MARKET: {d['original_market']['name']}")
        print(f"     Hours remaining: {d['original_market']['hours']}h")
        print(f"     Price per kg:    ${d['original_market']['price_per_kg']:.2f}")
        print(f"     Quality at arr.: {d['original_market']['projected_quality_pct']:.1f}%")
        print(f"     Net revenue:     ${d['original_market']['net_revenue_usd']:,.0f}")

        if d["best_alternative"]:
            alt = d["best_alternative"]
            print(f"\n  [REROUTE] BEST ALTERNATIVE: {alt['name']}")
            print(f"     Hours to reach:  {alt['hours']}h")
            print(f"     Price per kg:    ${alt['price_per_kg']:.2f}")
            print(f"     Quality at arr.: {alt['projected_quality_pct']:.1f}%")
            print(f"     Net revenue:     ${alt['net_revenue_usd']:,.0f}")
            print(f"     Rerouting cost:  ${alt['rerouting_cost_usd']:,.0f}")

        print()
        print(f"  [USD] NET ARBITRAGE:   ${d['net_arbitrage_margin_usd']:,.0f} (mock)")
        print(f"  [NOTE] RECOMMENDATION:  {d['recommendation']}")
        print(f"  [INFO] REASON: {d['recommendation_reason']}")

    print("\n" + "=" * 70)
    print("Note: All prices and calculations are mock demonstrations.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_arbitrage_demo()
