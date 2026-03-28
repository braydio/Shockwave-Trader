"""Discord collector for bounded social sentiment ingestion."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from arbiter.collectors.base import BaseCollector, NormalizedEvent
from arbiter.config.settings import (
    DISCORD_BOT_TOKEN,
    DISCORD_SIGNAL_CHANNELS,
    STORAGE_DIR,
)


@dataclass
class RawDiscordMessage:
    """Canonical raw message payload for Discord fetches."""

    message_id: int
    content: str
    author: str
    timestamp: str
    channel_id: int
    channel: str
    attachments: int
    embeds: int
    raw: dict


class DiscordCollector(BaseCollector):
    """Collect signals from configured Discord channels."""

    name = "discord"
    priority = 4
    category = "social"

    BULLISH_KEYWORDS = [
        "oil",
        "crude",
        "energy",
        "supply disruption",
        "cut production",
        "inventory draw",
        "opec",
        "tanker",
        "pipeline",
        "rally",
        "surge",
        "spike",
    ]

    BEARISH_KEYWORDS = [
        "demand",
        "oversupply",
        "recession",
        "crash",
        "inventory build",
        "production increase",
        "plunge",
    ]

    ENERGY_ENTITIES = [
        "oil",
        "crude",
        "energy",
        "xle",
        "uso",
        "opec",
        "nat gas",
        "gasoline",
    ]

    def __init__(
        self,
        token: Optional[str] = None,
        channel_ids: Optional[list[int]] = None,
        messages_limit: int = 50,
    ):
        self.token = token or DISCORD_BOT_TOKEN
        self.channel_ids = channel_ids or DISCORD_SIGNAL_CHANNELS
        self.messages_limit = messages_limit
        self._storage_dir = Path(STORAGE_DIR)
        self._state_file = self._storage_dir / "discord_state.json"
        self._messages: list[RawDiscordMessage] = []

    def _load_state(self) -> dict[str, int]:
        if not self._state_file.exists():
            return {}
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, state: dict[str, int]) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    async def fetch(self) -> dict:
        """Fetch recent unseen messages from configured channels."""
        if not self.token:
            return {"messages": [], "error": "No Discord bot token"}
        if not self.channel_ids:
            return {"messages": [], "error": "DISCORD_SIGNAL_CHANNELS is empty"}

        self._messages = []

        try:
            import discord
        except ImportError:
            return {"messages": [], "error": "discord.py is not installed"}

        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True

        client = discord.Client(intents=intents)

        @client.event
        async def on_ready():
            try:
                await self._collect_history(client)
            finally:
                await client.close()

        try:
            await client.start(self.token)
        except Exception as exc:
            return {"messages": [], "error": str(exc)}

        return {"messages": [message.__dict__ for message in self._messages]}

    async def _collect_history(self, client) -> None:
        state = self._load_state()
        new_state = dict(state)

        for channel_id in self.channel_ids:
            try:
                channel = client.get_channel(channel_id)
                if channel is None:
                    channel = await client.fetch_channel(channel_id)
            except Exception:
                continue

            last_seen = state.get(str(channel_id), 0)
            collected = []

            try:
                async for message in channel.history(limit=self.messages_limit):
                    if message.author.bot:
                        continue
                    if message.id <= last_seen:
                        continue
                    content = (message.content or "").strip()
                    if not content:
                        continue
                    collected.append(message)
            except Exception:
                continue

            for message in reversed(collected):
                self._messages.append(
                    RawDiscordMessage(
                        message_id=message.id,
                        content=(message.content or "").strip(),
                        author=str(message.author),
                        timestamp=message.created_at.astimezone(UTC).isoformat(),
                        channel_id=channel_id,
                        channel=getattr(channel, "name", str(channel_id)),
                        attachments=len(getattr(message, "attachments", []) or []),
                        embeds=len(getattr(message, "embeds", []) or []),
                        raw={
                            "message_id": message.id,
                            "channel_id": channel_id,
                            "jump_url": getattr(message, "jump_url", ""),
                            "transport": "discord_gateway",
                        },
                    )
                )
                new_state[str(channel_id)] = max(
                    new_state.get(str(channel_id), 0), message.id
                )

        self._save_state(new_state)

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        """Convert Discord messages to normalized events."""
        messages = raw.get("messages", [])
        events = []
        seen_ids: set[str] = set()

        for payload in messages:
            try:
                message = RawDiscordMessage(**payload)
            except (TypeError, KeyError):
                continue

            message_key = f"{message.channel_id}:{message.message_id}"
            if message_key in seen_ids:
                continue
            seen_ids.add(message_key)

            event = self._message_to_event(message)
            if event:
                events.append(event)

        return events

    def _message_to_event(
        self, message: RawDiscordMessage
    ) -> Optional[NormalizedEvent]:
        """Convert a message to a normalized event."""
        content = message.content.lower()

        if not content or len(content) < 10:
            return None

        entities = self._extract_entities(content)
        if not entities:
            return None

        direction, magnitude = self._classify(content)
        confidence = self._calculate_confidence(message)

        if confidence < 0.3:
            return None

        return NormalizedEvent(
            id=f"discord_{message.channel_id}_{message.message_id}",
            timestamp=message.timestamp,
            source=self.name,
            category=self.category,
            entities=entities,
            direction=direction,
            magnitude=magnitude,
            confidence=confidence,
            raw={
                "content": content,
                "author": message.author,
                "channel": message.channel,
                "channel_id": message.channel_id,
                "attachments": message.attachments,
                "embeds": message.embeds,
                "transport": message.raw.get("transport", "unknown"),
            },
        )

    def _extract_entities(self, text: str) -> list[str]:
        entities = []
        text_lower = text.lower()

        for entity in self.ENERGY_ENTITIES:
            if entity in text_lower:
                entities.append(entity)

        if "middle east" in text_lower:
            entities.append("middle east")
        if "opec" in text_lower:
            entities.append("opec")

        return list(dict.fromkeys(entities))[:5]

    def _classify(self, text: str) -> tuple[str, float]:
        bullish_count = sum(1 for keyword in self.BULLISH_KEYWORDS if keyword in text)
        bearish_count = sum(1 for keyword in self.BEARISH_KEYWORDS if keyword in text)

        total = bullish_count + bearish_count
        if total == 0:
            return "neutral", 0.3

        magnitude = min(0.3 + (total * 0.15), 1.0)

        if bullish_count > bearish_count:
            return "bullish", magnitude
        if bearish_count > bullish_count:
            return "bearish", magnitude
        return "neutral", 0.3

    def _calculate_confidence(self, message: RawDiscordMessage) -> float:
        confidence = 0.4
        text = message.content

        if len(text) > 50:
            confidence += 0.2
        if len(text) > 100:
            confidence += 0.1
        if "http" in text or "www" in text:
            confidence += 0.1
        if message.attachments > 0:
            confidence += 0.05
        if message.embeds > 0:
            confidence += 0.05

        return min(confidence, 0.9)


async def test():
    """Test the collector."""
    collector = DiscordCollector()

    print("[DiscordCollector] Fetching messages...")
    raw = await collector.fetch()

    if raw.get("error"):
        print(f"[DiscordCollector] Error: {raw['error']}")
        print("[DiscordCollector] Set DISCORD_BOT_TOKEN and DISCORD_SIGNAL_CHANNELS")
        return

    print(f"[DiscordCollector] Fetched {len(raw.get('messages', []))} messages")

    events = collector.transform(raw)
    print(f"[DiscordCollector] Generated {len(events)} events")

    for event in events[:3]:
        print(f"  [{event.direction}] {event.entities}")
        print(f"    {event.raw.get('content', '')[:60]}...")


if __name__ == "__main__":
    asyncio.run(test())
