"""Configuration settings for Arbiter."""

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional for bare interpreter validation

    def load_dotenv() -> None:
        """No-op fallback when python-dotenv is not installed."""


load_dotenv()


def _get_int(name: str, default: int = 0) -> int:
    """Read an integer environment variable with a safe fallback."""
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_list(name: str) -> list[str]:
    """Read a comma-separated environment variable into a list."""
    value = os.getenv(name, "").strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]

# Public Brokerage API
PUBLIC_API_KEY = os.getenv("PUBLIC_API_KEY", "")
PUBLIC_API_ACCESS_TOKEN = os.getenv("PUBLIC_API_ACCESS_TOKEN", PUBLIC_API_KEY)
PUBLIC_API_SECRET_KEY = os.getenv("PUBLIC_API_SECRET_KEY", "")
PUBLIC_API_BASE = os.getenv("PUBLIC_API_BASE", "https://api.public.com")
PUBLIC_ACCOUNT_ID = os.getenv("PUBLIC_ACCOUNT_ID", "")

# Execution config
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.2"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "4"))
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "10"))
DEFAULT_TRADE_AMOUNT = float(os.getenv("DEFAULT_TRADE_AMOUNT", "500"))

# FRED API (free key from fred.stlouisfed.org)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# EIA API (free key from eia.gov)
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

# Telegram (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_ID = _get_int("TELEGRAM_API_ID", 0)
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "arbiter")
TELEGRAM_SOURCE_CHATS = _get_list("TELEGRAM_SOURCE_CHATS")

# Discord Notifications
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_NOTIFICATIONS_ENABLED = (
    os.getenv("DISCORD_NOTIFICATIONS_ENABLED", "false").lower() == "true"
)
DISCORD_SIGNALS_ENABLED = (
    os.getenv("DISCORD_SIGNALS_ENABLED", "false").lower() == "true"
)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_SIGNAL_CHANNELS = [
    int(item) for item in _get_list("DISCORD_SIGNAL_CHANNELS") if item.isdigit()
]

# Execution Backend
# Options: "public", "paper", "auto" (default)
EXECUTION_BACKEND = os.getenv("EXECUTION_BACKEND", "auto")

# Local paper trading
PAPER_STARTING_CASH = float(os.getenv("PAPER_STARTING_CASH", "10000"))
PAPER_STATE_FILE = os.getenv("PAPER_STATE_FILE", "storage/paper_account.json")

# Storage
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
LOG_DIR = os.getenv("LOG_DIR", "storage/logs")

# Scheduler
CYCLE_INTERVAL_SECONDS = int(os.getenv("CYCLE_INTERVAL_SECONDS", "300"))

# OpenAI advisor
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))
OPENAI_ADVISOR_ENABLED = (
    os.getenv("OPENAI_ADVISOR_ENABLED", "false").lower() == "true"
)

# Signal thresholds
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.7"))
MIN_MAGNITUDE = float(os.getenv("MIN_MAGNITUDE", "0.5"))
