"""Trade logging utilities for Arbiter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from arbiter.config.settings import STORAGE_DIR


class TradeLogger:
    """Append-only JSONL trade logger for execution decisions and broker responses."""

    def __init__(self, storage_dir: Optional[str] = None, filename: str = "trade_log.jsonl"):
        self.storage_dir = Path(storage_dir or STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.storage_dir / filename

    def log_trade(
        self,
        decision: dict[str, Any],
        order: dict[str, Any] | Any,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append a trade execution record."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "order": self._serialize(order),
            "metadata": metadata or {},
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def read_trades(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent trade log entries."""
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return [json.loads(line) for line in lines[-limit:]]

    @staticmethod
    def _serialize(value: Any) -> Any:
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return value
