"""GDELT collector for event-driven energy news."""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from arbiter.collectors.base import BaseCollector


class GDELTCollector(BaseCollector):
    """Collect energy-relevant event news from the GDELT doc API."""

    name = "gdelt"
    priority = 3
    category = "news"

    ENERGY_KEYWORDS = [
        "oil",
        "energy",
        "opec",
        "pipeline",
        "tanker",
        "refinery",
        "middle east",
        "brent",
        "wti",
        "shipping",
        "sanctions",
    ]

    BULLISH_KEYWORDS = [
        "outage",
        "attack",
        "disruption",
        "sanctions",
        "tightening",
        "shortage",
        "escalation",
        "strike",
    ]

    BEARISH_KEYWORDS = [
        "ceasefire",
        "surplus",
        "cooling",
        "easing",
        "restart",
        "production increase",
        "inventory build",
        "output increase",
    ]

    def __init__(self, max_articles: int = 10):
        self.max_articles = max_articles

    async def fetch(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> dict[str, Any]:
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "format": "json",
                "mode": "artlist",
                "maxrecords": self.max_articles,
                "query": "oil OR opec OR pipeline OR tanker OR refinery OR energy",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def transform(self, raw: dict[str, Any]) -> list:
        articles = raw.get("articles", []) if isinstance(raw, dict) else []
        events = []

        for article in articles[: self.max_articles]:
            text = " ".join(
                [
                    article.get("title", ""),
                    article.get("seendate", ""),
                    article.get("sourceCountry", ""),
                    article.get("domain", ""),
                ]
            ).lower()
            entities = [keyword for keyword in self.ENERGY_KEYWORDS if keyword in text]
            if not entities:
                entities = ["energy"]

            bullish_hits = sum(keyword in text for keyword in self.BULLISH_KEYWORDS)
            bearish_hits = sum(keyword in text for keyword in self.BEARISH_KEYWORDS)
            if bullish_hits > bearish_hits:
                direction = "bullish"
            elif bearish_hits > bullish_hits:
                direction = "bearish"
            else:
                direction = "neutral"

            magnitude = min(0.35 + 0.1 * (bullish_hits + bearish_hits + len(entities)), 1.0)
            confidence = min(0.55 + 0.05 * len(entities), 0.8)

            events.append(
                self._make_event(
                    entities=entities,
                    direction=direction,
                    magnitude=magnitude,
                    confidence=confidence,
                    raw={
                        "title": article.get("title", ""),
                        "url": article.get("url"),
                        "seendate": article.get("seendate", ""),
                        "domain": article.get("domain", ""),
                        "bullish_hits": bullish_hits,
                        "bearish_hits": bearish_hits,
                        "tags": entities,
                    },
                )
            )

        return events
