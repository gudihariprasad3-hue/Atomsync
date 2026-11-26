"""
============================================================
AtmoSync – Pipeline Orchestrator (Module G)
============================================================

Lightweight scheduler that orchestrates the full AtmoSync
pipeline WITHOUT requiring Airflow or a cloud scheduler.

Schedule options:
  1. Manual: python orchestration/pipeline_runner.py --once
  2. Continuous: python orchestration/pipeline_runner.py --interval 300
  3. Cron-style: set a Windows Task Scheduler job pointing to --once

What it does each run:
  1. Generates new sensor readings (simulator)
  2. Publishes to Kafka topic (or file fallback)
  3. Runs spoilage + arbitrage calculations
  4. Writes results to output file
  5. Fires alerts where thresholds are breached
  6. (Optional) triggers dbt run via subprocess

Usage:
  python orchestration/pipeline_runner.py --once
  python orchestration/pipeline_runner.py --interval 300   # every 5 min
  python orchestration/pipeline_runner.py --dbt            # also runs dbt
============================================================
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Ensure project root is on path ──────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from simulator.sensor_generator import SensorSimulator, SIMULATOR_CONFIG
from analytics.spoilage_engine import SpoilageEngine
from analytics.arbitrage_engine import ArbitrageEngine
from alerts.alert_manager import AlertManager

# ── Logging setup ────────────────────────────────────────────────────────────
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "pipeline.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("atmosync.pipeline")

# ── Output directory ─────────────────────────────────────────────────────────
OUTPUT_DIR = ROOT / "data" / "pipeline_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# PIPELINE STEPS
# ============================================================

def step_simulate(simulator: SensorSimulator) -> list[dict]:
    """Step 1 – Generate sensor readings for all containers."""
    log.info("Step 1: Generating sensor readings...")
    readings = simulator.generate_all_readings()
    log.info("  Generated %d readings.", len(readings))
    return readings


def step_calculate_analytics(
    readings: list[dict],
    spoilage_engine: SpoilageEngine,
    arbitrage_engine: ArbitrageEngine,
) -> list[dict]:
    """Steps 2 & 3 – Calculate spoilage and arbitrage for each reading."""
    log.info("Step 2: Calculating spoilage and arbitrage...")
    results = []
    for reading in readings:
        spoilage = spoilage_engine.calculate(reading)
        arb = arbitrage_engine.analyze(reading, hours_to_original=48.0)
        results.append({
            "reading": reading,
            "spoilage": spoilage.to_dict(),
            "arbitrage": arb.to_dict(),
        })
        log.info(
            "  %s | %s | spoilage=%.1f%% | risk=%s | recommendation=%s",
            reading["container_id"],
            reading["commodity"],
            spoilage.spoilage_score * 100,
            spoilage.risk_level,
            arb.recommendation,
        )
    return results


def step_write_output(results: list[dict]) -> Path:
    """Step 4 – Persist pipeline results to a JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_file = OUTPUT_DIR / f"pipeline_run_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_containers": len(results),
                "results": results,
            },
            fh,
            indent=2,
        )
    log.info("Step 4: Output written to %s", out_file)
    return out_file


def step_fire_alerts(results: list[dict], alert_manager: AlertManager) -> int:
    """Step 5 – Fire alerts for critical findings."""
    log.info("Step 5: Checking alert thresholds...")
    fired = 0
    from analytics.spoilage_engine import SpoilageResult

    for r in results:
        # Reconstruct spoilage result for alert check
        # to_dict() structure: top-level keys + nested "contributions" and "inputs"
        s = r["spoilage"]
        contrib = s.get("contributions", {})
        inputs = s.get("inputs", {})
        spoilage_result = SpoilageResult(
            container_id=s["container_id"],
            commodity=s["commodity"],
            hours_in_transit=inputs.get("hours_in_transit", 0.0),
            base_transit_spoilage=contrib.get("base_transit", 0.0),
            temp_spoilage_contribution=contrib.get("temperature", 0.0),
            humidity_spoilage_contribution=contrib.get("humidity", 0.0),
            vibration_spoilage_contribution=contrib.get("vibration", 0.0),
            spoilage_score=s["spoilage_score"],
            quality_remaining_pct=s["quality_remaining_pct"],
            estimated_hours_remaining=s["estimated_hours_remaining"],
            risk_level=s["risk_level"],
            temperature_c=inputs.get("temperature_c", 0.0),
            humidity_pct=inputs.get("humidity_pct", 0.0),
            vibration_ms2=inputs.get("vibration_ms2", 0.0),
            temp_deviation_c=inputs.get("temp_deviation_c", 0.0),
            humidity_deviation_pct=inputs.get("humidity_deviation_pct", 0.0),
        )
        alert = alert_manager.check_and_alert_spoilage(spoilage_result)
        if alert:
            fired += 1
            log.warning(
                "  ALERT fired: %s – %s [%s]",
                alert.container_id, alert.title, alert.severity,
            )

        # Arbitrage alert – fire a direct alert for RECOMMEND_REROUTE cases
        arb = r["arbitrage"]
        if arb["recommendation"] == "RECOMMEND_REROUTE":
            from alerts.alert_manager import Alert
            best = arb.get("best_alternative") or {}
            arb_alert = Alert(
                alert_type="ARBITRAGE_OPPORTUNITY",
                container_id=arb["container_id"],
                commodity=arb["commodity"],
                severity="WARNING",
                title=f"Reroute Opportunity: {arb['container_id']}",
                message=arb.get("recommendation_reason", "Rerouting recommended."),
                details={
                    "net_arbitrage_margin_usd": arb.get("net_arbitrage_margin_usd"),
                    "recommended_market": best.get("market_name"),
                    "hours_to_alt": best.get("hours_to_reach"),
                },
            )
            alert_manager.send_alert(arb_alert)
            fired += 1
            log.warning(
                "  ARBITRAGE ALERT: %s – %s",
                arb["container_id"], arb_alert.title,
            )

    log.info("  %d alert(s) fired.", fired)
    return fired


def step_run_dbt() -> bool:
    """Step 6 (optional) – Run dbt models."""
    log.info("Step 6: Running dbt models...")
    dbt_dir = ROOT / "dbt"
    try:
        result = subprocess.run(
            ["dbt", "run", "--profiles-dir", str(dbt_dir)],
            cwd=str(dbt_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            log.info("  dbt run completed successfully.")
            return True
        else:
            log.error("  dbt run failed:\n%s", result.stderr)
            return False
    except FileNotFoundError:
        log.warning("  dbt not installed or not in PATH. Skipping dbt run.")
        return False
    except subprocess.TimeoutExpired:
        log.error("  dbt run timed out after 300 seconds.")
        return False


# ============================================================
# MAIN PIPELINE RUNNER
# ============================================================

def run_pipeline(run_dbt: bool = False) -> dict:
    """Execute one full pipeline run. Returns a summary dict."""
    start = time.time()
    run_ts = datetime.now(timezone.utc).isoformat()

    log.info("=" * 56)
    log.info("AtmoSync Pipeline Run – %s", run_ts)
    log.info("=" * 56)

    # Disable Kafka and file output for orchestrator mode
    SIMULATOR_CONFIG.output_to_kafka = False
    SIMULATOR_CONFIG.output_to_file = False

    simulator = SensorSimulator()
    spoilage_engine = SpoilageEngine()
    arbitrage_engine = ArbitrageEngine()
    alert_manager = AlertManager()

    readings = step_simulate(simulator)
    results = step_calculate_analytics(readings, spoilage_engine, arbitrage_engine)
    out_file = step_write_output(results)
    alerts_fired = step_fire_alerts(results, alert_manager)

    dbt_ok = None
    if run_dbt:
        dbt_ok = step_run_dbt()

    elapsed = time.time() - start
    summary = {
        "run_timestamp": run_ts,
        "containers_processed": len(readings),
        "alerts_fired": alerts_fired,
        "output_file": str(out_file),
        "dbt_run": dbt_ok,
        "elapsed_seconds": round(elapsed, 2),
    }

    log.info("Pipeline run complete in %.2fs | %d containers | %d alerts", 
             elapsed, len(readings), alerts_fired)
    log.info("=" * 56)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="AtmoSync Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python orchestration/pipeline_runner.py --once
  python orchestration/pipeline_runner.py --interval 300
  python orchestration/pipeline_runner.py --once --dbt
        """,
    )
    parser.add_argument("--once", action="store_true",
                        help="Run the pipeline once and exit.")
    parser.add_argument("--interval", type=int, metavar="SECONDS",
                        help="Run the pipeline every N seconds continuously.")
    parser.add_argument("--dbt", action="store_true",
                        help="Also run dbt models after each pipeline run.")
    args = parser.parse_args()

    if args.once:
        run_pipeline(run_dbt=args.dbt)

    elif args.interval:
        log.info("Continuous mode: running every %ds. Press Ctrl+C to stop.", args.interval)
        run_count = 0
        try:
            while True:
                run_count += 1
                log.info("--- Run #%d ---", run_count)
                run_pipeline(run_dbt=args.dbt)
                log.info("Next run in %ds...", args.interval)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            log.info("Pipeline stopped by user after %d run(s).", run_count)

    else:
        # Default: run once
        run_pipeline(run_dbt=args.dbt)


if __name__ == "__main__":
    main()
