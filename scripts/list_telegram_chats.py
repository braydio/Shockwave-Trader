#!/usr/bin/env python3
"""List Telegram chats visible to the configured Telethon session."""

from __future__ import annotations

from dotenv import load_dotenv
import asyncio
import sys
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

load_dotenv()

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

from arbiter.config.settings import (
    STORAGE_DIR,
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION_NAME,
)


async def main() -> None:
    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        print("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
        raise SystemExit(1)

    try:
        from telethon import TelegramClient
    except ImportError:
        print("Telethon is not installed in this environment")
        raise SystemExit(1)

    session_path = str((ROOT / STORAGE_DIR / TELEGRAM_SESSION_NAME).resolve())
    client = TelegramClient(session_path, TELEGRAM_API_ID, TELEGRAM_API_HASH)

    await client.start()
    print("Visible Telegram chats:\n")
    print(
        "Suggested values for TELEGRAM_SOURCE_CHATS are the username when present, otherwise the numeric id.\n"
    )

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        username = getattr(entity, "username", None)
        identifier = f"@{username}" if username else str(dialog.id)
        title = dialog.name or "(no title)"
        kind = type(entity).__name__
        print(f"{identifier:<25} | {title:<40} | {kind}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
