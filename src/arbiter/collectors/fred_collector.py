"""FRED collector for macro regime context."""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from arbiter.collectors.base import BaseCollector, NormalizedEvent
from arbiter.config.settings import FRED_API_KEY


class FREDCollector(BaseCollector):
    """Collect macro indicators from FRED."""

    name = "fred"
    priority = 2
    category = "macro"

    SERIES = {
        "DGS10": "10Y Treasury",
        "DGS2": "2Y Treasury",
        "VIXCLS": "VIX",
        "DCOILWTICO": "WTI Crude",
    }

    async def fetch(self) -> dict[str, dict[str, float]]:
        if not FRED_API_KEY:
            return {}
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> dict[str, dict[str, float]]:
        data: dict[str, dict[str, float]] = {}
        for series_id, name in self.SERIES.items():
            response = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "api_key": FRED_API_KEY,
                    "file_type": "json",
                    "series_id": series_id,
                    "sort_order": "desc",
                    "limit": 2,
                },
                timeout=30,
            )
            response.raise_for_status()
            observations = response.json().get("observations", [])
            values = [
                float(item["value"])
                for item in observations
                if item.get("value") not in {None, "."}
            ]
            if not values:
                continue
            data[series_id] = {
                "name": name,
                "value": values[0],
                "previous": values[1] if len(values) > 1 else values[0],
            }
        return data

    def transform(self, raw: dict[str, dict[str, float]]) -> list[NormalizedEvent]:
        events: list[NormalizedEvent] = []

        ten_year = raw.get("DGS10", {}).get("value")
        two_year = raw.get("DGS2", {}).get("value")
        if ten_year is not None and two_year is not None:
            slope = ten_year - two_year
            events.append(
                self._make_event(
                    entities=["yield_curve", "macro"],
                    direction="bullish" if slope > 0 else "bearish",
                    magnitude=min(abs(slope) / 2.0, 1.0),
                    confidence=0.85,
                    raw={"indicator": "yield_curve", "slope": slope, "tags": ["macro", "rates"]},
                )
            )

        vix = raw.get("VIXCLS", {}).get("value")
        if vix is not None:
            events.append(
                self._make_event(
                    entities=["volatility", "risk_regime"],
                    direction="bearish" if vix >= 25 else "bullish",
                    magnitude=min(vix / 50.0, 1.0),
                    confidence=0.9,
                    raw={"indicator": "vix", "value": vix, "tags": ["volatility", "macro"]},
                )
            )

        oil = raw.get("DCOILWTICO", {}).get("value")
        oil_prev = raw.get("DCOILWTICO", {}).get("previous")
        if oil is not None and oil_prev is not None:
            change_pct = ((oil - oil_prev) / oil_prev * 100) if oil_prev else 0.0
            events.append(
                self._make_event(
                    entities=["oil", "energy", "wti"],
                    direction="bullish" if change_pct >= 0 else "bearish",
                    magnitude=min(abs(change_pct) / 10.0, 1.0),
                    confidence=0.8,
                    raw={
                        "indicator": "wti",
                        "value": oil,
                        "previous": oil_prev,
                        "change_pct": change_pct,
                        "tags": ["oil", "energy", "macro"],
                    },
                )
            )

        return events
