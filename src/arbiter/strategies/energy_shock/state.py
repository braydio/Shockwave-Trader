"""State management for energy shock strategy."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import json

from arbiter.strategies.energy_shock.strategy import PositionState


@dataclass
class StrategyState:
    """Persistent state for strategy."""

    position: PositionState | None = None
    last_trade_time: datetime | None = None
    last_signal_time: datetime | None = None
    consecutive_holds: int = 0


class StateManager:
    """Manage strategy state persistence."""

    def __init__(self, state_file: str = "storage/energy_shock_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state: StrategyState | None = None

    def load(self) -> StrategyState:
        """Load state from file."""
        if self._state is not None:
            return self._state

        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                position = None
                if data.get("position"):
                    p = data["position"]
                    position = PositionState(
                        symbol=p["symbol"],
                        entry_price=p["entry_price"],
                        entry_date=datetime.fromisoformat(p["entry_date"]),
                        quantity=p["quantity"],
                        peak_price=p.get("peak_price", p["entry_price"]),
                        partial_exited=p.get("partial_exited", False),
                    )

                self._state = StrategyState(
                    position=position,
                    last_trade_time=datetime.fromisoformat(data["last_trade_time"])
                    if data.get("last_trade_time")
                    else None,
                    last_signal_time=datetime.fromisoformat(data["last_signal_time"])
                    if data.get("last_signal_time")
                    else None,
                    consecutive_holds=data.get("consecutive_holds", 0),
                )
            except Exception:
                self._state = StrategyState()
        else:
            self._state = StrategyState()

        return self._state

    def save(self):
        """Save state to file."""
        if self._state is None:
            return

        position_data = None
        if self._state.position:
            p = self._state.position
            position_data = {
                "symbol": p.symbol,
                "entry_price": p.entry_price,
                "entry_date": p.entry_date.isoformat(),
                "quantity": p.quantity,
                "peak_price": p.peak_price,
                "partial_exited": p.partial_exited,
            }

        data = {
            "position": position_data,
            "last_trade_time": self._state.last_trade_time.isoformat()
            if self._state.last_trade_time
            else None,
            "last_signal_time": self._state.last_signal_time.isoformat()
            if self._state.last_signal_time
            else None,
            "consecutive_holds": self._state.consecutive_holds,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        self.state_file.write_text(json.dumps(data, indent=2))

    def update_position(self, position: PositionState | None):
        """Update current position."""
        state = self.load()
        state.position = position
        if position:
            state.last_trade_time = datetime.now(UTC)
        self.save()

    def update_signal(self):
        """Update last signal time."""
        state = self.load()
        state.last_signal_time = datetime.now(UTC)
        self.save()

    def increment_holds(self):
        """Increment consecutive hold counter."""
        state = self.load()
        state.consecutive_holds += 1
        self.save()

    def reset_holds(self):
        """Reset consecutive hold counter."""
        state = self.load()
        state.consecutive_holds = 0
        self.save()

    def clear(self):
        """Clear all state."""
        self._state = StrategyState()
        if self.state_file.exists():
            self.state_file.unlink()
