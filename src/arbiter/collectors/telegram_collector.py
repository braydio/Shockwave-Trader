"""Telegram collector — MTProto (Telethon) for reading channels and groups.

Design principles:
- Telethon user session (NOT Bot API) for reading real channels
- Multi-channel support with per-channel message deduplication
- Only fetches NEW messages each cycle (stores last_seen_id per channel)
- Energy-domain entity extraction + direction/magnitude/confidence scoring
- Graceful degradation: falls back to Bot API if MTProto not configured
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from arbiter.collectors.base import BaseCollector, NormalizedEvent
from arbiter.config.settings import (
    STORAGE_DIR,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_SESSION_NAME,
    TELEGRAM_SOURCE_CHATS,
    TELEGRAM_BOT_TOKEN,
)


@dataclass
class RawMessage:
    """Canonical raw message schema from Telegram."""

    message_id: int
    text: str
    timestamp: str
    channel: str
    channel_title: str
    views: int
    forwards: int
    raw: dict


ENTITY_KEYWORDS: dict[str, list[str]] = {
    "oil": ["oil", "crude", "crude oil", "brent", "wti", "opec", "urals"],
    "energy": ["energy", "energy sector", "energy market"],
    "nat_gas": ["natural gas", "nat gas", "lng", "liquified natural gas"],
    "gasoline": ["gasoline", "petrol", "refinery"],
    "geopolitical": [
        "middle east",
        "persian gulf",
        "strait of hormuz",
        "saudi",
        "iran",
        "iraq",
        "russia",
        "ukraine",
        "sanctions",
        "isis",
        "houthi",
    ],
    "shipping": ["tanker", "tankers", "shipping", "suez canal", "red sea"],
    "pipeline": ["pipeline", "pipelines", "nord stream"],
    "macro": ["inflation", "cpi", "fed", "rate hike", "recession", "dollar"],
}

BULLISH_SIGNALS: dict[str, float] = {
    "attack": 0.7,
    "disruption": 0.6,
    "halted": 0.5,
    "shortage": 0.7,
    "sanctions": 0.6,
    "explosion": 0.7,
    "drone": 0.6,
    "strike": 0.5,
    "seized": 0.6,
    "blockade": 0.7,
    "confiscated": 0.5,
    "breaking": 0.4,
    "emergency": 0.5,
    "cut production": 0.7,
    "output cut": 0.7,
    "deepening": 0.5,
    "escalation": 0.6,
    "outage": 0.6,
    "shutdown": 0.5,
    "alert": 0.4,
}

BEARISH_SIGNALS: dict[str, float] = {
    "ceasefire": 0.6,
    "restart": 0.5,
    "surplus": 0.6,
    "increase supply": 0.7,
    "output rise": 0.6,
    "inventory build": 0.5,
    "inventory draw": -0.4,
    "demand destruction": 0.7,
    "recession": 0.6,
    "rate cut": 0.4,
    "negotiations": 0.3,
    "deal": 0.4,
    "agreement": 0.4,
    "output increase": 0.6,
    "surge": -0.3,
    "plunge": -0.4,
    "crash": -0.5,
}

URGENT_TERMS = [
    "breaking",
    "urgent",
    "alert",
    "just in",
    "developing",
    "now",
    "confirmed",
    "live",
    "flash",
    "warning",
]


def extract_entities(text: str) -> list[str]:
    """Extract energy-domain entities from message text."""
    text_lower = text.lower()
    found: list[str] = []
    for entity, keywords in ENTITY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(entity)
    return found


def score_direction(text: str) -> tuple[str, float]:
    """Infer direction and return confidence from signal keywords.

    Returns:
        Tuple of (direction, magnitude)
    """
    text_lower = text.lower()
    bullish_score = 0.0
    bearish_score = 0.0

    for keyword, weight in BULLISH_SIGNALS.items():
        if keyword in text_lower:
            bullish_score += weight

    for keyword, weight in BEARISH_SIGNALS.items():
        if keyword in text_lower:
            bearish_score += abs(weight)

    # Bullish EIA events like "inventory draw" reduce bearish signal
    if "inventory draw" in text_lower:
        bearish_score -= 0.4

    net = bullish_score - bearish_score

    if net > 0.5:
        direction = "bullish"
        magnitude = min(0.5 + net * 0.1, 1.0)
    elif net < -0.5:
        direction = "bearish"
        magnitude = min(0.5 + abs(net) * 0.1, 1.0)
    else:
        direction = "neutral"
        magnitude = 0.3

    return direction, magnitude


def score_urgency(text: str) -> float:
    """Score urgency from alert keywords."""
    text_lower = text.lower()
    hits = sum(1 for term in URGENT_TERMS if term in text_lower)
    return min(0.4 + hits * 0.15, 1.0)


def score_confidence(views: int, forwards: int, text: str) -> float:
    """Score confidence from engagement metrics and content quality."""
    confidence = 0.45

    if views >= 1000:
        confidence += 0.15
    elif views >= 100:
        confidence += 0.05

    if forwards >= 10:
        confidence += 0.10
    elif forwards >= 1:
        confidence += 0.05

    if len(text) > 100:
        confidence += 0.10
    elif len(text) > 50:
        confidence += 0.05

    if any(term in text.lower() for term in ["source:", "according to", "reports"]):
        confidence += 0.05

    return min(confidence, 0.92)


def is_noise(text: str) -> bool:
    """Filter garbage messages."""
    text_lower = text.lower()
    if len(text) < 25:
        return True
    if any(
        kw in text_lower
        for kw in [
            "subscribe",
            "follow for more",
            "dm for",
            "whatsapp",
            "signal channel",
            "paid group",
            "premium access",
            "🎯",
            "📈",
            "📉",
            "💰",
            "click here",
            "t.me/",
        ]
    ):
        return True
    return False


class TelegramCollector(BaseCollector):
    """Collect signals from Telegram channels via Telethon (MTProto).

    Supports:
    - Multiple channels per cycle
    - Deduplication via per-channel last_seen_id
    - Bot API fallback if MTProto not configured
    """

    name = "telegram"
    priority = 4
    category = "social"

    _client: Optional[object] = None
    _client_lock: asyncio.Lock = asyncio.Lock()

    def __init__(
        self,
        api_id: Optional[int] = None,
        api_hash: Optional[str] = None,
        session_name: Optional[str] = None,
        chats: Optional[list[str]] = None,
        messages_limit: int = 50,
    ):
        self.api_id = api_id or TELEGRAM_API_ID
        self.api_hash = api_hash or TELEGRAM_API_HASH
        self.session_name = session_name or TELEGRAM_SESSION_NAME or "arbiter"
        self.chats = chats or TELEGRAM_SOURCE_CHATS
        self.messages_limit = messages_limit
        self._storage_dir = Path(STORAGE_DIR)
        self._state_file = self._storage_dir / "telegram_state.json"
        self._messages: list[RawMessage] = []

    def _load_state(self) -> dict[str, int]:
        """Load last seen message IDs per channel."""
        if not self._state_file.exists():
            return {}
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_state(self, state: dict[str, int]) -> None:
        """Persist last seen message IDs per channel."""
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    async def _get_client(self) -> Optional[object]:
        """Lazily initialize and return the Telethon client (singleton)."""
        if not self.api_id or not self.api_hash:
            return None

        if TelegramCollector._client is not None:
            return TelegramCollector._client

        async with TelegramCollector._client_lock:
            if TelegramCollector._client is not None:
                return TelegramCollector._client

            try:
                from telethon import TelegramClient
            except ImportError:
                return None

            session_path = str(self._storage_dir / self.session_name)
            TelegramCollector._client = TelegramClient(
                session_path,
                self.api_id,
                self.api_hash,
            )
            return TelegramCollector._client

    async def fetch(self) -> dict:
        """Fetch new messages from all configured channels.

        Returns:
            Dict with 'messages' key containing list of RawMessage dicts.
        """
        self._messages = []

        if self.api_id and self.api_hash and not self.chats:
            if TELEGRAM_BOT_TOKEN:
                await self._fetch_bot()
                return {"messages": [m.__dict__ for m in self._messages]}
            return {
                "messages": [],
                "error": "Telethon configured but TELEGRAM_SOURCE_CHATS is empty",
            }

        # Try MTProto (user session)
        if self.api_id and self.api_hash:
            await self._fetch_mtproto()
        # Fallback: Bot API
        elif TELEGRAM_BOT_TOKEN:
            await self._fetch_bot()
        else:
            return {"messages": [], "error": "No Telegram credentials configured"}

        return {"messages": [m.__dict__ for m in self._messages]}

    async def _fetch_mtproto(self) -> None:
        """Fetch via Telethon MTProto — reads real channels."""
        client = await self._get_client()
        if client is None:
            return

        try:
            if not client.is_connected():
                await client.start()
        except Exception:
            return

        state = self._load_state()
        new_state = dict(state)

        for chat in self.chats:
            try:
                last_seen = state.get(chat, 0)
                msgs = []
                async for message in client.iter_messages(
                    chat,
                    min_id=last_seen,
                    limit=self.messages_limit,
                ):
                    if message.text and message.text.strip():
                        msgs.append(message)

                # Process newest first
                for msg in reversed(msgs):
                    text = (msg.text or msg.message or "").strip()
                    if not text or is_noise(text):
                        continue

                    self._messages.append(
                        RawMessage(
                            message_id=msg.id,
                            text=text,
                            timestamp=datetime.fromtimestamp(
                                msg.date.timestamp(), tz=UTC
                            ).isoformat()
                            if msg.date
                            else datetime.now(UTC).isoformat(),
                            channel=chat,
                            channel_title=getattr(msg.chat, "title", chat) or chat,
                            views=getattr(msg, "views", 0) or 0,
                            forwards=getattr(msg, "forwards", 0) or 0,
                            raw={
                                "message_id": msg.id,
                                "chat_id": msg.chat_id,
                                "chat_title": getattr(msg.chat, "title", chat),
                                "date": str(msg.date) if msg.date else None,
                                "transport": "telethon",
                            },
                        )
                    )

                    new_state[chat] = max(new_state.get(chat, 0), msg.id)

            except Exception:
                continue

        self._save_state(new_state)

    async def _fetch_bot(self) -> None:
        """Fallback: Bot API via requests (no channel reading, only bot chats)."""
        import requests

        if not TELEGRAM_BOT_TOKEN:
            return

        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"limit": 20, "timeout": 0},
                timeout=10,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])

            state = self._load_state()
            new_state = dict(state)

            for update in updates:
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue

                text = (msg.get("text") or msg.get("caption") or "").strip()
                if not text or is_noise(text):
                    continue

                msg_id = msg.get("message_id", 0)
                chat_id = str(msg.get("chat", {}).get("id", "unknown"))
                last_seen = state.get(chat_id, 0)

                if msg_id <= last_seen:
                    continue

                self._messages.append(
                    RawMessage(
                        message_id=msg_id,
                        text=text,
                        timestamp=datetime.fromtimestamp(
                            msg.get("date", 0), tz=UTC
                        ).isoformat(),
                        channel=chat_id,
                        channel_title=msg.get("chat", {}).get("title", chat_id)
                        or chat_id,
                        views=msg.get("views", 0) or 0,
                        forwards=msg.get("forward_count", 0) or 0,
                        raw={**msg, "transport": "bot_api"},
                    )
                )
                new_state[chat_id] = max(new_state.get(chat_id, 0), msg_id)

            self._save_state(new_state)
        except Exception:
            return

    def transform(self, raw: dict) -> list[NormalizedEvent]:
        """Convert raw messages to normalized events.

        Args:
            raw: Dict with 'messages' list of RawMessage dicts

        Returns:
            List of NormalizedEvent objects
        """
        messages_raw = raw.get("messages", [])
        events: list[NormalizedEvent] = []
        seen_ids: set[str] = set()

        for msg_data in messages_raw:
            try:
                msg = RawMessage(**msg_data)
            except (TypeError, KeyError):
                continue

            text = msg.text
            msg_id_str = f"{msg.channel}:{msg.message_id}"

            if msg_id_str in seen_ids:
                continue
            seen_ids.add(msg_id_str)

            entities = extract_entities(text)
            if not entities:
                continue

            direction, dir_magnitude = score_direction(text)
            urgency = score_urgency(text)
            confidence = score_confidence(msg.views, msg.forwards, text)

            magnitude = min(dir_magnitude * 0.7 + urgency * 0.3, 1.0)

            if magnitude < 0.3:
                continue

            events.append(
                self._make_event(
                    entities=entities,
                    direction=direction,
                    magnitude=magnitude,
                    confidence=confidence,
                    raw={
                        "message_id": msg.message_id,
                        "channel": msg.channel,
                        "channel_title": msg.channel_title,
                        "text": text,
                        "views": msg.views,
                        "forwards": msg.forwards,
                        "urgency": urgency,
                        "direction_magnitude": dir_magnitude,
                        "tags": entities,
                        "transport": msg.raw.get("transport", "unknown"),
                    },
                )
            )

        return events

    async def run(self) -> list[NormalizedEvent]:
        """Full fetch + transform pipeline."""
        raw = await self.fetch()
        return self.transform(raw)

    @classmethod
    async def close(cls) -> None:
        """Disconnect the shared Telethon client."""
        if cls._client is not None:
            try:
                await cls._client.disconnect()
            except Exception:
                pass
            cls._client = None
