"""EIA collector for energy-market context."""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from arbiter.collectors.base import BaseCollector, NormalizedEvent
from arbiter.config.settings import EIA_API_KEY


class EIACollector(BaseCollector):
    """Collect EIA petroleum spot price context."""

    name = "eia"
    priority = 5
    category = "commodity"

    async def fetch(self) -> dict[str, Any]:
        if not EIA_API_KEY:
            return {}
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> dict[str, Any]:
        response = requests.get(
            "https://api.eia.gov/v2/petroleum/pri/spt/data/",
            params={
                "api_key": EIA_API_KEY,
                "frequency": "daily",
                "data[0]": "value",
                "facets[product][]": "EPCBRENT",
                "facets[duoarea][]": "ZEU",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "offset": 0,
                "length": 2,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def transform(self, raw: dict[str, Any]) -> list[NormalizedEvent]:
        rows = raw.get("response", {}).get("data", []) if isinstance(raw, dict) else []
        if not rows:
            return []

        latest = rows[0]
        previous = rows[1] if len(rows) > 1 else rows[0]
        latest_value = float(latest.get("value", 0.0) or 0.0)
        previous_value = float(previous.get("value", latest_value) or latest_value)
        change_pct = (
            ((latest_value - previous_value) / previous_value) * 100
            if previous_value
            else 0.0
        )

        return [
            self._make_event(
                entities=["oil", "energy", "brent"],
                direction="bullish" if change_pct >= 0 else "bearish",
                magnitude=min(abs(change_pct) / 8.0, 1.0),
                confidence=0.85,
                raw={
                    "series": "brent_spot",
                    "latest": latest_value,
                    "previous": previous_value,
                    "change_pct": change_pct,
                    "period": latest.get("period"),
                    "tags": ["oil", "energy", "inventory_draw"],
                },
            )
        ]
