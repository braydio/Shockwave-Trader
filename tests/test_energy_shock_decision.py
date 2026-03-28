from __future__ import annotations

import tempfile
import unittest

from arbiter.execution.public_client import Account, Position
from arbiter.strategies.energy_shock import EnergyShockDecisionEngine, StrategyConfig
from arbiter.strategies.energy_shock.state import StateManager


class FakeClient:
    def __init__(self, *, equity: float = 10000.0, buying_power: float = 5000.0, positions=None):
        self._account = Account(
            account_id="brok-1",
            buying_power=buying_power,
            cash=buying_power,
            equity=equity,
        )
        self._positions = positions or []

    def get_account(self) -> Account:
        return self._account

    def get_positions(self) -> list[Position]:
        return self._positions

    def get_position(self, symbol: str):
        for position in self._positions:
            if position.symbol == symbol:
                return position
        return None


class EnergyShockDecisionTests(unittest.TestCase):
    def test_evaluate_emits_entry_trade_when_signal_and_budget_are_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = EnergyShockDecisionEngine(
                client=FakeClient(),
                state_manager=StateManager(state_file=f"{tmpdir}/state.json"),
                config=StrategyConfig(
                    trade_confidence_min=0.5,
                    event_pressure_min=0.5,
                    market_confirmation_min=0.3,
                    risk_regime_min=0.3,
                    base_usd=500.0,
                    max_position_pct=0.05,
                ),
            )

            decision = engine.evaluate(
                market_data={
                    "XLE": {"price": 92.0, "change_pct": 1.4},
                    "USO": {"price": 80.0, "change_pct": 1.5},
                    "SPY": {"price": 520.0, "change_pct": 0.2},
                    "VIXY": {"price": 18.0, "change_pct": -0.5},
                },
                event_pressure=0.8,
            )

            self.assertEqual(decision.status, "entry")
            self.assertIsNotNone(decision.trade)
            self.assertEqual(decision.trade.side, "buy")
            self.assertEqual(decision.trade.symbol, "XLE")
            self.assertGreater(decision.trade.amount_usd, 0)

    def test_evaluate_emits_exit_trade_when_existing_position_should_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Position(
                symbol="XLE",
                qty=4,
                market_value=320.0,
                unrealized_pl=-25.0,
                current_price=80.0,
            )
            engine = EnergyShockDecisionEngine(
                client=FakeClient(positions=[existing]),
                state_manager=StateManager(state_file=f"{tmpdir}/state.json"),
                config=StrategyConfig(),
            )

            decision = engine.evaluate(
                market_data={
                    "XLE": {"price": 80.0, "change_pct": -3.0},
                    "USO": {"price": 70.0, "change_pct": -1.5},
                    "SPY": {"price": 510.0, "change_pct": -1.0},
                    "VIXY": {"price": 30.0, "change_pct": 2.0},
                },
                event_pressure=0.1,
            )

            self.assertEqual(decision.status, "exit")
            self.assertIsNotNone(decision.trade)
            self.assertEqual(decision.trade.side, "sell")
            self.assertEqual(decision.trade.qty, 4)


if __name__ == "__main__":
    unittest.main()
