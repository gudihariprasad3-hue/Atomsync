# AtmoSync – Spoilage & Arbitrage Calculations

> **DISCLAIMER**: All calculations in this document and in the AtmoSync codebase use **simplified mock formulas for demonstration purposes only**. They are **NOT** scientifically validated spoilage models and should **NOT** be used for real-world commodity trading decisions.

---

## 1. Spoilage Score Model

The spoilage score is a number from **0.0** (perfectly fresh) to **1.0** (fully spoiled).

### Formula

```
spoilage_score = min(
    base_transit_spoilage
    + temp_spoilage_contribution
    + humidity_spoilage_contribution
    + vibration_spoilage_contribution,
    1.0
)
```

### Component Calculations

| Component | Formula | Cap |
|---|---|---|
| Base transit | `hours_in_transit / (shelf_life_days × 24)` | 1.0 |
| Temperature | `temp_deviation_°C × 0.015 × hours_in_transit` | 0.5 |
| Humidity | `humidity_deviation_% × 0.008` | 0.2 |
| Vibration | `vibration_excess_m/s² × 0.05` | 0.15 |

**temperature deviation** = max(actual_temp - optimal_max, optimal_min - actual_temp, 0)  
**humidity deviation** = max(optimal_min_humidity - actual_humidity, 0)  
**vibration excess** = max(actual_vibration - 1.5 m/s² warning threshold, 0)

### Risk Levels

| Risk Level | Spoilage Score Range |
|---|---|
| LOW_RISK | 0.0 – 0.35 |
| MEDIUM_RISK | 0.35 – 0.60 |
| HIGH_RISK | 0.60 – 0.80 |
| CRITICAL_RISK | 0.80 – 1.0 |

### Commodity Shelf Lives (Mock Values)

| Commodity | Optimal Temp (°C) | Mock Shelf Life |
|---|---|---|
| Avocado | 4–7 | 21 days |
| Strawberry | 0–4 | 7 days |
| Banana | 13–15 | 14 days |
| Mango | 10–13 | 18 days |
| Tomato | 10–12 | 10 days |

---

## 2. Arbitrage Margin Calculation

### Projected Quality at Destination

For each potential market, we project how much quality remains when the cargo arrives:

```
additional_spoilage = hours_to_market × 0.02 × (1 + current_spoilage)
projected_spoilage = min(current_spoilage + additional_spoilage, 1.0)
projected_quality = 1.0 - projected_spoilage
```

### Revenue Projections (Mock)

```
gross_revenue = market_price_per_kg × quantity_kg × projected_quality
net_revenue   = gross_revenue - rerouting_cost
```

### Net Arbitrage Margin

```
net_arbitrage_margin = alt_market_net_revenue - original_market_net_revenue
```

### Rerouting Cost Estimate (Mock)

```
rerouting_cost = $200 (base) + $50 × hours_to_alternative_market
```

### Recommendation Logic

| Condition | Recommendation |
|---|---|
| Alt market has >10% quality AND original has 0% quality | RECOMMEND_REROUTE |
| Alt net revenue > min_margin ($500) + current margin | RECOMMEND_REROUTE |
| Risk = HIGH_RISK or CRITICAL_RISK AND margin > $500 | RECOMMEND_REROUTE |
| Risk = HIGH_RISK or CRITICAL_RISK AND margin ≤ $500 | EVALUATE_REROUTE |
| All other cases | STAY_ON_COURSE |

---

## 3. Mock Price Assumptions

All prices below are **illustrative only**. They do not represent real market prices.

| Commodity | Base Price | Range across markets |
|---|---|---|
| Avocado | $2.50/kg | $2.30 – $2.50 |
| Strawberry | $4.80/kg | $4.32 – $4.80 |
| Banana | $1.20/kg | $1.14 – $1.22 |
| Mango | $3.20/kg | $3.14 – $3.46 |
| Tomato | $1.80/kg | $1.66 – $1.80 |

---

## 4. Important Limitations

1. **No real food science**: The spoilage formula is a simplified linear model, not a validated biological spoilage curve.
2. **No real prices**: All commodity prices are fixed mock values, not live market data.
3. **No real routes**: Transit times are fixed assumptions, not live logistics data.
4. **No external factors**: Seasonality, demand, regulations, and actual container conditions are not modeled.
5. **Demonstration only**: This system is built to demonstrate data engineering architecture, not to make actual trading recommendations.
