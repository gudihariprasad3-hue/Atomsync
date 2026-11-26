"""
============================================================
AtmoSync – Alert Manager (Module G)
============================================================

WHAT THIS DOES:
    Sends alerts when spoilage or arbitrage thresholds
    are exceeded. Supports:
      - Console logging (always)
      - Local log file (always)
      - Slack webhook (if configured)
      - Email via SMTP (if configured)

HOW TO TEST:
    python alerts/alert_manager.py

HOW TO CONFIGURE EXTERNAL ALERTS:
    1. Slack: Set SLACK_WEBHOOK_URL in your .env file
       Get your webhook at: https://api.slack.com/messaging/webhooks

    2. Email: Set these in your .env file:
       ALERT_EMAIL_FROM=your_email@gmail.com
       ALERT_EMAIL_TO=recipient@example.com
       ALERT_EMAIL_PASSWORD=your_app_password
       (Use Gmail App Password, not regular password)
============================================================
"""

import os
import sys
import json
import logging
import smtplib
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Alert log file path
ALERT_LOG_FILE = Path("logs/alerts.log")
ALERT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


# ============================================================
# ALERT DATA CLASS
# ============================================================

@dataclass
class Alert:
    """Represents a single alert event."""
    alert_type: str             # SPOILAGE_WARNING, ARBITRAGE_OPPORTUNITY, CRITICAL_SENSOR
    container_id: str
    commodity: str
    severity: str               # INFO, WARNING, CRITICAL
    title: str
    message: str
    details: Dict[str, Any]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type,
            "container_id": self.container_id,
            "commodity": self.commodity,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }

    def to_slack_blocks(self) -> Dict[str, Any]:
        """Format alert as Slack Block Kit message."""
        severity_emoji = {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️",
        }.get(self.severity, "📢")

        return {
            "text": f"{severity_emoji} AtmoSync Alert: {self.title}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{severity_emoji} {self.title}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Container:*\n{self.container_id}"},
                        {"type": "mrkdwn", "text": f"*Commodity:*\n{self.commodity}"},
                        {"type": "mrkdwn", "text": f"*Severity:*\n{self.severity}"},
                        {"type": "mrkdwn", "text": f"*Time:*\n{self.timestamp}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*\n{self.message}",
                    },
                },
                {"type": "divider"},
            ],
        }


# ============================================================
# ALERT CHANNELS
# ============================================================

class LocalLogChannel:
    """Write alerts to a local log file (always available)."""

    def send(self, alert: Alert) -> bool:
        """Write alert to log file."""
        try:
            with open(ALERT_LOG_FILE, "a") as f:
                f.write(json.dumps(alert.to_dict()) + "\n")
            return True
        except Exception as e:
            logger.error(f"Failed to write alert log: {e}")
            return False


class SlackChannel:
    """Send alerts to Slack via webhook."""

    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith("https://"))

    def send(self, alert: Alert) -> bool:
        """Send alert to Slack. Returns True if successful."""
        if not self.is_configured():
            logger.debug("Slack not configured. Skipping.")
            return False

        try:
            payload = alert.to_slack_blocks()
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                logger.info(f"Slack alert sent: {alert.title}")
                return True
            else:
                logger.error(f"Slack returned {response.status_code}: {response.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Slack send failed: {e}")
            return False


class EmailChannel:
    """Send alerts via email (Gmail SMTP)."""

    def __init__(self):
        self.from_email = os.getenv("ALERT_EMAIL_FROM", "")
        self.to_email = os.getenv("ALERT_EMAIL_TO", "")
        self.password = os.getenv("ALERT_EMAIL_PASSWORD", "")
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587

    def is_configured(self) -> bool:
        return bool(self.from_email and self.to_email and self.password)

    def send(self, alert: Alert) -> bool:
        """Send alert via email. Returns True if successful."""
        if not self.is_configured():
            logger.debug("Email not configured. Skipping.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[AtmoSync Alert] {alert.title}"
            msg["From"] = self.from_email
            msg["To"] = self.to_email

            # Plain text body
            text_body = (
                f"AtmoSync Alert\n"
                f"{'='*50}\n"
                f"Container: {alert.container_id}\n"
                f"Commodity: {alert.commodity}\n"
                f"Severity:  {alert.severity}\n"
                f"Time:      {alert.timestamp}\n\n"
                f"{alert.message}\n\n"
                f"Details: {json.dumps(alert.details, indent=2)}\n\n"
                f"-- AtmoSync Micro-Climate Analytics --\n"
            )

            # HTML body
            html_body = f"""
            <html><body>
            <h2 style="color: {'red' if alert.severity=='CRITICAL' else 'orange'}">
                AtmoSync Alert: {alert.title}
            </h2>
            <table>
                <tr><td><b>Container:</b></td><td>{alert.container_id}</td></tr>
                <tr><td><b>Commodity:</b></td><td>{alert.commodity}</td></tr>
                <tr><td><b>Severity:</b></td><td>{alert.severity}</td></tr>
                <tr><td><b>Time:</b></td><td>{alert.timestamp}</td></tr>
            </table>
            <p>{alert.message}</p>
            <pre>{json.dumps(alert.details, indent=2)}</pre>
            </body></html>
            """

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.from_email, self.password)
                server.sendmail(self.from_email, self.to_email, msg.as_string())

            logger.info(f"Email alert sent to {self.to_email}: {alert.title}")
            return True

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False


# ============================================================
# ALERT MANAGER
# ============================================================

class AlertManager:
    """
    Central alert manager. Routes alerts to all configured channels.
    Always logs to local file. Optionally sends to Slack and email.
    """

    # Load thresholds from environment
    SPOILAGE_THRESHOLD = float(os.getenv("ALERT_SPOILAGE_THRESHOLD", "0.70"))
    ARBITRAGE_MIN_MARGIN = float(os.getenv("ALERT_ARBITRAGE_MIN_MARGIN", "500.00"))

    def __init__(self):
        self.channels = [
            LocalLogChannel(),
            SlackChannel(),
            EmailChannel(),
        ]
        self._alerts_sent = 0

    def send_alert(self, alert: Alert) -> Dict[str, bool]:
        """
        Send alert through all configured channels.
        Returns dict of channel name → success.
        """
        results = {}
        self._alerts_sent += 1

        # Always log to console
        severity_symbol = {"CRITICAL": "🚨", "WARNING": "⚠️", "INFO": "ℹ️"}.get(
            alert.severity, "📢"
        )
        print(f"\n{severity_symbol} ALERT [{alert.severity}]: {alert.title}")
        print(f"   Container: {alert.container_id} | {alert.commodity}")
        print(f"   {alert.message}")

        for channel in self.channels:
            channel_name = type(channel).__name__
            try:
                success = channel.send(alert)
                results[channel_name] = success
            except Exception as e:
                logger.error(f"{channel_name} send error: {e}")
                results[channel_name] = False

        return results

    def check_and_alert_spoilage(self, spoilage_result) -> Optional[Alert]:
        """Check a spoilage result and send alert if threshold exceeded."""
        if spoilage_result.spoilage_score >= self.SPOILAGE_THRESHOLD:
            alert = Alert(
                alert_type="SPOILAGE_WARNING",
                container_id=spoilage_result.container_id,
                commodity=spoilage_result.commodity,
                severity="CRITICAL" if spoilage_result.spoilage_score >= 0.85 else "WARNING",
                title=f"Spoilage Alert: {spoilage_result.container_id}",
                message=(
                    f"Container {spoilage_result.container_id} has reached "
                    f"{spoilage_result.spoilage_score*100:.1f}% spoilage (mock estimate). "
                    f"Risk level: {spoilage_result.risk_level}. "
                    f"Estimated {spoilage_result.estimated_hours_remaining:.1f}h remaining."
                ),
                details={
                    "spoilage_score": round(spoilage_result.spoilage_score, 4),
                    "risk_level": spoilage_result.risk_level,
                    "hours_remaining": round(spoilage_result.estimated_hours_remaining, 1),
                    "temperature_c": spoilage_result.temperature_c,
                    "disclaimer": "Mock calculation – not scientifically validated",
                },
            )
            self.send_alert(alert)
            return alert
        return None

    def check_and_alert_arbitrage(self, arbitrage_result) -> Optional[Alert]:
        """Check an arbitrage result and send alert if opportunity found."""
        if (arbitrage_result.recommendation == "RECOMMEND_REROUTE" and
                arbitrage_result.net_arbitrage_margin_usd > self.ARBITRAGE_MIN_MARGIN):
            alt = arbitrage_result.best_alternative
            alert = Alert(
                alert_type="ARBITRAGE_OPPORTUNITY",
                container_id=arbitrage_result.container_id,
                commodity=arbitrage_result.commodity,
                severity="WARNING",
                title=f"Arbitrage Opportunity: {arbitrage_result.container_id}",
                message=(
                    f"Rerouting {arbitrage_result.container_id} to "
                    f"{alt.market_name if alt else 'alternative market'} "
                    f"could save ${arbitrage_result.net_arbitrage_margin_usd:,.0f} "
                    f"(mock estimate)."
                ),
                details={
                    "net_arbitrage_usd": round(arbitrage_result.net_arbitrage_margin_usd, 2),
                    "recommended_market": alt.market_name if alt else None,
                    "recommended_city": alt.city if alt else None,
                    "hours_to_market": alt.hours_to_reach if alt else None,
                    "disclaimer": "Mock prices – not real market data",
                },
            )
            self.send_alert(alert)
            return alert
        return None

    def get_alert_history(self) -> List[Dict]:
        """Read all alerts from the local log file."""
        if not ALERT_LOG_FILE.exists():
            return []
        alerts = []
        with open(ALERT_LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        alerts.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return alerts


# ============================================================
# STANDALONE TEST
# ============================================================

def test_alert_manager():
    """Test the alert manager with mock data."""
    from analytics.spoilage_engine import SpoilageEngine
    from analytics.arbitrage_engine import ArbitrageEngine

    logging.basicConfig(level=logging.INFO)
    manager = AlertManager()

    print("=" * 60)
    print("AtmoSync Alert Manager Test")
    print("=" * 60)

    # Create a critical reading
    critical_reading = {
        "container_id": "CTR-001",
        "commodity": "AVOCADO",
        "temperature_celsius": 16.0,
        "humidity_percent": 68.0,
        "vibration_ms2": 2.5,
        "hours_in_transit": 55.0,
    }

    # Test spoilage alert
    spoilage_engine = SpoilageEngine()
    spoilage_result = spoilage_engine.calculate(critical_reading)
    print(f"\nSpoilage score: {spoilage_result.spoilage_score*100:.1f}%")
    print(f"Alert threshold: {manager.SPOILAGE_THRESHOLD*100:.0f}%")

    alert = manager.check_and_alert_spoilage(spoilage_result)
    if alert:
        print("✅ Spoilage alert triggered and sent to configured channels")
    else:
        print("ℹ️  Spoilage below threshold – no alert")

    # Test arbitrage alert
    arbitrage_engine = ArbitrageEngine()
    arbitrage_result = arbitrage_engine.analyze(critical_reading, hours_to_original=120.0)
    print(f"\nArbitrage margin: ${arbitrage_result.net_arbitrage_margin_usd:,.0f}")
    print(f"Recommendation: {arbitrage_result.recommendation}")

    alert = manager.check_and_alert_arbitrage(arbitrage_result)
    if alert:
        print("✅ Arbitrage alert triggered and sent to configured channels")
    else:
        print("ℹ️  No arbitrage alert triggered")

    # Show alert log
    history = manager.get_alert_history()
    print(f"\n📋 Alert log has {len(history)} total alerts. Location: {ALERT_LOG_FILE}")
    print("\n✅ Alert manager test complete.")

    print("\n📌 TO CONFIGURE SLACK/EMAIL ALERTS:")
    print("   1. Copy .env.example to .env")
    print("   2. Set SLACK_WEBHOOK_URL or email settings")
    print("   3. Re-run this script to test external delivery")


if __name__ == "__main__":
    test_alert_manager()
