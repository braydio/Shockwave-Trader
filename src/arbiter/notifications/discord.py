"""Discord notifications for Arbiter.

Sends trade alerts and signal updates to Discord via webhook.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import requests

from arbiter.lib.logger import setup_logger

logger = setup_logger("arbiter.notifications")


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    SIGNAL = "signal"
    ENTRY = "entry"
    EXIT = "exit"
    ERROR = "error"


@dataclass
class TradeAlert:
    """Trade alert data."""

    level: AlertLevel
    symbol: str
    side: str
    qty: float
    price: float
    confidence: float
    reasoning: str
    pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None


class DiscordNotifier:
    """Send alerts to Discord via webhook."""

    def __init__(self, webhook_url: str, enabled: bool = True):
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)
        self.session = requests.Session()

    def _send(self, payload: dict) -> bool:
        """Send payload to Discord webhook."""
        if not self.enabled:
            return False

        try:
            response = self.session.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.debug(
                f"Discord notification sent: {payload.get('embeds', [{}])[0].get('title', 'N/A')}"
            )
            return True
        except Exception as e:
            logger.error(f"Discord notification failed: {e}")
            return False

    def _embed(
        self,
        title: str,
        description: str,
        color: int,
        fields: Optional[list] = None,
        footer: Optional[str] = None,
    ) -> dict:
        """Create Discord embed."""
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if fields:
            embed["fields"] = fields

        if footer:
            embed["footer"] = {"text": footer}

        return embed

    def send_trade(self, alert: TradeAlert):
        """Send trade alert to Discord."""
        if alert.level == AlertLevel.ENTRY:
            title = f"🚀 ENTRY: {alert.side.upper()} {alert.symbol}"
            color = 0x00FF00  # Green
            description = f"**Confidence:** {alert.confidence:.1%}\n**Qty:** {alert.qty:g} @ ${alert.price:.2f}"
        elif alert.level == AlertLevel.EXIT:
            title = f"🏁 EXIT: {alert.symbol}"
            color = 0xFF6600  # Orange
            pnl_str = f"{alert.pnl_pct:+.2%}" if alert.pnl_pct is not None else "N/A"
            description = f"**Reason:** {alert.exit_reason}\n**P&L:** {pnl_str}"
        else:
            title = f"📊 {alert.side.upper()} {alert.symbol}"
            color = 0x0099FF  # Blue
            description = f"Qty: {alert.qty:g} @ ${alert.price:.2f}"

        fields = [
            {"name": "Reasoning", "value": alert.reasoning[:1024], "inline": False},
        ]

        embed = self._embed(
            title=title,
            description=description,
            color=color,
            fields=fields,
            footer="Arbiter Trading System",
        )

        self._send({"embeds": [embed]})

    def send_signal(self, signal_data: dict):
        """Send signal update to Discord."""
        embed = self._embed(
            title="📈 Signal Update",
            description=f"Confidence: **{signal_data.get('confidence', 0):.1%}**",
            color=0x0099FF,
            fields=[
                {
                    "name": "Action",
                    "value": signal_data.get("action", "hold"),
                    "inline": True,
                },
                {
                    "name": "Event Pressure",
                    "value": f"{signal_data.get('event_pressure', 0):.2f}",
                    "inline": True,
                },
                {
                    "name": "Market Confirm",
                    "value": f"{signal_data.get('market_confirmation', 0):.2f}",
                    "inline": True,
                },
                {
                    "name": "Risk Regime",
                    "value": f"{signal_data.get('risk_regime', 0):.2f}",
                    "inline": True,
                },
                {
                    "name": "Cycle",
                    "value": str(signal_data.get("cycle", 0)),
                    "inline": True,
                },
            ],
            footer=f"Arbiter | {datetime.now().strftime('%H:%M')}",
        )

        self._send({"embeds": [embed]})

    def send_error(self, error_message: str, context: str = ""):
        """Send error alert to Discord."""
        embed = self._embed(
            title="⚠️ Arbiter Error",
            description=error_message[:2048],
            color=0xFF0000,  # Red
            fields=[{"name": "Context", "value": context or "N/A", "inline": False}]
            if context
            else [],
            footer="Arbiter Error Alert",
        )

        self._send({"embeds": [embed]})

    def send_status(self, message: str, cycle: int = 0):
        """Send periodic status update."""
        embed = self._embed(
            title=f"📊 Arbiter Status (Cycle {cycle})",
            description=message,
            color=0x666666,  # Gray
            footer=f"Last update: {datetime.now().strftime('%H:%M:%S')}",
        )

        self._send({"embeds": [embed]})


def create_discord_notifier() -> DiscordNotifier:
    """Create Discord notifier from settings."""
    from arbiter.config.settings import (
        DISCORD_WEBHOOK_URL,
        DISCORD_NOTIFICATIONS_ENABLED,
    )

    return DiscordNotifier(
        webhook_url=DISCORD_WEBHOOK_URL or "", enabled=DISCORD_NOTIFICATIONS_ENABLED
    )
