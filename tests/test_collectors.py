from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from arbiter.collectors.discord_collector import DiscordCollector
from arbiter.collectors.eia_collector import EIACollector
from arbiter.collectors.fred_collector import FREDCollector
from arbiter.collectors.gdelt_collector import GDELTCollector
from arbiter.collectors.telegram_collector import TelegramCollector


class CollectorTransformTests(unittest.TestCase):
    def test_fred_transform_builds_macro_and_energy_events(self) -> None:
        collector = FREDCollector()
        events = collector.transform(
            {
                "DGS10": {"value": 4.2, "previous": 4.1},
                "DGS2": {"value": 3.9, "previous": 3.8},
                "VIXCLS": {"value": 18.0, "previous": 17.5},
                "DCOILWTICO": {"value": 82.0, "previous": 80.0},
            }
        )

        self.assertEqual(len(events), 3)
        self.assertTrue(any("yield_curve" in event.entities for event in events))
        self.assertTrue(any("oil" in event.entities for event in events))

    def test_eia_transform_builds_energy_event(self) -> None:
        collector = EIACollector()
        events = collector.transform(
            {
                "response": {
                    "data": [
                        {"period": "2026-03-20", "value": "84.0"},
                        {"period": "2026-03-19", "value": "81.0"},
                    ]
                }
            }
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "eia")
        self.assertIn("oil", events[0].entities)

    def test_gdelt_transform_builds_news_events(self) -> None:
        collector = GDELTCollector(max_articles=2)
        events = collector.transform(
            {
                "articles": [
                    {
                        "title": "Pipeline outage raises oil market concerns",
                        "url": "https://example.com/1",
                        "seendate": "20260320T120000Z",
                        "sourceCountry": "US",
                    }
                ]
            }
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "gdelt")
        self.assertIn("pipeline", events[0].entities)
        self.assertEqual(events[0].direction, "bullish")

    def test_discord_transform_builds_social_event(self) -> None:
        collector = DiscordCollector()
        events = collector.transform(
            {
                "messages": [
                    {
                        "message_id": 11,
                        "content": "Breaking: oil tanker disruption confirmed in key shipping lane",
                        "author": "EnergyBot",
                        "timestamp": "2026-03-20T12:00:00Z",
                        "channel_id": 123,
                        "channel": "energy-signals",
                        "attachments": 0,
                        "embeds": 0,
                        "raw": {"transport": "discord_gateway"},
                    }
                ]
            }
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "discord")
        self.assertIn("oil", events[0].entities)
        self.assertGreaterEqual(events[0].confidence, 0.3)
        self.assertEqual(events[0].raw["transport"], "discord_gateway")

    def test_discord_fetch_requires_signal_channels(self) -> None:
        collector = DiscordCollector(
            token="discord-token",
            channel_ids=[],
        )

        raw = asyncio.run(collector.fetch())

        self.assertEqual(raw["messages"], [])
        self.assertIn("DISCORD_SIGNAL_CHANNELS", raw["error"])

    def test_telegram_transform_builds_social_event_with_urgency(self) -> None:
        collector = TelegramCollector()
        events = collector.transform(
            {
                "messages": [
                    {
                        "message_id": 11,
                        "text": "Breaking: oil tanker disruption confirmed in key shipping lane",
                        "timestamp": "2026-03-20T12:00:00Z",
                        "channel": "@OilEnergyAlerts",
                        "channel_title": "Oil Energy Alerts",
                        "views": 5420,
                        "forwards": 23,
                        "raw": {},
                    }
                ]
            }
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "telegram")
        self.assertIn("oil", events[0].entities)
        self.assertGreaterEqual(events[0].raw["urgency"], 0.4)
        self.assertGreaterEqual(events[0].confidence, 0.5)

    def test_telegram_transform_filters_noise(self) -> None:
        collector = TelegramCollector()
        events = collector.transform(
            {
                "messages": [
                    {
                        "message_id": 1,
                        "text": "Subscribe for more",
                        "timestamp": "",
                        "channel": "c",
                        "channel_title": "c",
                        "views": 0,
                        "forwards": 0,
                        "raw": {},
                    },
                    {
                        "message_id": 2,
                        "text": "hi",
                        "timestamp": "",
                        "channel": "c",
                        "channel_title": "c",
                        "views": 0,
                        "forwards": 0,
                        "raw": {},
                    },
                    {
                        "message_id": 3,
                        "text": "BREAKING: Drone attack on Saudi oil facility causes major supply disruption — markets reacting",
                        "timestamp": "",
                        "channel": "c",
                        "channel_title": "c",
                        "views": 12000,
                        "forwards": 150,
                        "raw": {},
                    },
                ]
            }
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "bullish")
        self.assertIn("oil", events[0].entities)

    def test_telegram_transform_bearish_signal(self) -> None:
        collector = TelegramCollector()
        events = collector.transform(
            {
                "messages": [
                    {
                        "message_id": 1,
                        "text": "OPEC agreement reached — output increase of 500k barrels confirmed, ceasefire in Libya allows exports to resume",
                        "timestamp": "",
                        "channel": "c",
                        "channel_title": "c",
                        "views": 8000,
                        "forwards": 90,
                        "raw": {},
                    },
                ]
            }
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "bearish")
        self.assertIn("oil", events[0].entities)

    def test_telegram_fetch_requires_source_chats_for_telethon_mode(self) -> None:
        with patch("arbiter.collectors.telegram_collector.TELEGRAM_BOT_TOKEN", ""):
            collector = TelegramCollector(
                api_id=12345,
                api_hash="hash",
                chats=[],
            )

            raw = asyncio.run(collector.fetch())

        self.assertEqual(raw["messages"], [])
        self.assertIn("TELEGRAM_SOURCE_CHATS", raw["error"])


if __name__ == "__main__":
    unittest.main()
