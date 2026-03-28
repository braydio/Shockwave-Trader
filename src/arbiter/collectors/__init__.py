"""Collector exports for Arbiter."""

from arbiter.collectors.base import BaseCollector, NormalizedEvent
from arbiter.collectors.discord_collector import DiscordCollector
from arbiter.collectors.eia_collector import EIACollector
from arbiter.collectors.fred_collector import FREDCollector
from arbiter.collectors.gdelt_collector import GDELTCollector
from arbiter.collectors.telegram_collector import TelegramCollector
from arbiter.collectors.yfinance_collector import YFinanceCollector

__all__ = [
    "BaseCollector",
    "DiscordCollector",
    "EIACollector",
    "FREDCollector",
    "GDELTCollector",
    "NormalizedEvent",
    "TelegramCollector",
    "YFinanceCollector",
]
