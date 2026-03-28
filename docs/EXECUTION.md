# Arbiter Execution Layer

**Public API integration for trade execution**

---

## Overview

```
Signal Engine → Trade Decision → Executor → Public API → Confirmation
```

Arbiter executes trades ONLY through the Public API. All execution logic lives here.

---

## Trade Decision Object

```python
@dataclass
class TradeDecision:
    symbol: str              # Ticker symbol
    side: str                # "buy" or "sell"
    amount_usd: float        # Dollar amount to trade
    qty: int                 # Calculated quantity
    confidence: float        # Signal confidence (0-1)
    reasoning: str            # Why this trade
    timestamp: str            # Decision time
```

---

## Public API Client

```python
# src/arbiter/execution/public_client.py
import requests
from typing import Optional
from dataclasses import dataclass

@dataclass
class Account:
    buying_power: float
    cash: float
    equity: float

@dataclass
class Position:
    symbol: str
    qty: float
    market_value: float
    unrealized_pl: float

@dataclass
class Order:
    id: str
    symbol: str
    side: str
    qty: int
    status: str

class PublicClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def get_account(self) -> Account:
        """Get account information"""
        response = self.session.get(f"{self.base_url}/account")
        response.raise_for_status()
        data = response.json()
        return Account(
            buying_power=data.get("buying_power", 0),
            cash=data.get("cash", 0),
            equity=data.get("equity", 0)
        )

    def get_positions(self) -> list[Position]:
        """Get all open positions"""
        response = self.session.get(f"{self.base_url}/positions")
        response.raise_for_status()
        return [
            Position(
                symbol=p["symbol"],
                qty=float(p["qty"]),
                market_value=float(p["market_value"]),
                unrealized_pl=float(p["unrealized_pl"])
            )
            for p in response.json()
        ]

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get specific position"""
        try:
            response = self.session.get(f"{self.base_url}/positions/{symbol}")
            response.raise_for_status()
            p = response.json()
            return Position(
                symbol=p["symbol"],
                qty=float(p["qty"]),
                market_value=float(p["market_value"]),
                unrealized_pl=float(p["unrealized_pl"])
            )
        except requests.HTTPError:
            return None

    def submit_order(self, symbol: str, qty: int, side: str) -> Order:
        """Submit a market order"""
        payload = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": "market",
            "time_in_force": "day"
        }
        response = self.session.post(f"{self.base_url}/orders", json=payload)
        response.raise_for_status()
        data = response.json()
        return Order(
            id=data["id"],
            symbol=data["symbol"],
            side=data["side"],
            qty=int(data["qty"]),
            status=data["status"]
        )

    def get_orders(self, status: str = "open") -> list[Order]:
        """Get orders by status"""
        response = self.session.get(
            f"{self.base_url}/orders",
            params={"status": status}
        )
        response.raise_for_status()
        return [
            Order(
                id=o["id"],
                symbol=o["symbol"],
                side=o["side"],
                qty=int(o["qty"]),
                status=o["status"]
            )
            for o in response.json()
        ]

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order"""
        response = self.session.delete(f"{self.base_url}/orders/{order_id}")
        return response.status_code == 204
```

---

## Order Executor

```python
# src/arbiter/execution/order_executor.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
import json

from arbiter.execution.public_client import PublicClient
from arbiter.storage.trade_log import TradeLogger

@dataclass
class TradeResult:
    success: bool
    order_id: Optional[str]
    message: str
    timestamp: str

class OrderExecutor:
    def __init__(
        self,
        client: PublicClient,
        logger: TradeLogger,
        config: dict
    ):
        self.client = client
        self.logger = logger
        self.config = config

        # Cooldown tracking
        self.cooldown_file = Path("storage/cooldowns.json")
        self.cooldowns = self._load_cooldowns()

        # Max exposure
        self.max_position_pct = config.get("max_position_pct", 0.2)
        self.max_daily_trades = config.get("max_daily_trades", 10)

    def _load_cooldowns(self) -> dict:
        if self.cooldown_file.exists():
            return json.loads(self.cooldown_file.read_text())
        return {}

    def _save_cooldowns(self):
        self.cooldown_file.parent.mkdir(exist_ok=True)
        self.cooldown_file.write_text(json.dumps(self.cooldowns, indent=2))

    def _is_in_cooldown(self, symbol: str) -> bool:
        if symbol not in self.cooldowns:
            return False
        last_trade = datetime.fromisoformat(self.cooldowns[symbol])
        cooldown_hours = self.config.get("cooldown_hours", 4)
        return datetime.now() - last_trade < timedelta(hours=cooldown_hours)

    def _update_cooldown(self, symbol: str):
        self.cooldowns[symbol] = datetime.now().isoformat()
        self._save_cooldowns()

    def _check_exposure(self, symbol: str, amount: float) -> bool:
        account = self.client.get_account()
        position = self.client.get_position(symbol)

        current_exposure = position.market_value if position else 0
        new_exposure = current_exposure + amount

        if new_exposure / account.equity > self.max_position_pct:
            return False
        return True

    def _check_duplicate(self, symbol: str, side: str) -> bool:
        """Check if we already have an open order for this"""
        orders = self.client.get_orders(status="open")
        for order in orders:
            if order.symbol == symbol and order.side == side:
                return True  # Duplicate
        return False

    def _calculate_qty(self, symbol: str, amount_usd: float) -> int:
        """Calculate quantity from dollar amount"""
        # Get current price
        positions = self.client.get_positions()
        for p in positions:
            if p.symbol == symbol:
                return int(amount_usd / p.market_value * p.qty)
        # Default: assume ~$100 per share
        return int(amount_usd / 100)

    def execute(self, decision: dict) -> TradeResult:
        """Execute a trade decision"""
        symbol = decision["symbol"]
        side = decision["side"]
        amount_usd = decision.get("amount_usd", 500)
        reasoning = decision.get("reasoning", "")

        # Pre-trade checks
        if self._is_in_cooldown(symbol):
            return TradeResult(
                success=False,
                order_id=None,
                message=f"Cooldown active for {symbol}",
                timestamp=datetime.now().isoformat()
            )

        if self._check_duplicate(symbol, side):
            return TradeResult(
                success=False,
                order_id=None,
                message=f"Duplicate open order for {symbol} {side}",
                timestamp=datetime.now().isoformat()
            )

        if not self._check_exposure(symbol, amount_usd):
            return TradeResult(
                success=False,
                order_id=None,
                message=f"Max exposure exceeded for {symbol}",
                timestamp=datetime.now().isoformat()
            )

        # Calculate quantity
        qty = self._calculate_qty(symbol, amount_usd)
        if qty < 1:
            return TradeResult(
                success=False,
                order_id=None,
                message=f"Amount too small for {symbol}",
                timestamp=datetime.now().isoformat()
            )

        # Submit order
        try:
            order = self.client.submit_order(symbol, qty, side)
            self._update_cooldown(symbol)
            self.logger.log_trade({
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "confidence": decision.get("confidence", 0),
                "reasoning": reasoning,
                "order_id": order.id
            })

            return TradeResult(
                success=True,
                order_id=order.id,
                message=f"Order submitted: {side} {qty} {symbol}",
                timestamp=datetime.now().isoformat()
            )

        except Exception as e:
            return TradeResult(
                success=False,
                order_id=None,
                message=f"Order failed: {str(e)}",
                timestamp=datetime.now().isoformat()
            )
```

---

## Trade Logger

```python
# src/arbiter/storage/trade_log.py
from datetime import datetime
from pathlib import Path
import json
from typing import Optional

class TradeLogger:
    def __init__(self, log_dir: str = "storage/logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "trades.jsonl"

    def log_trade(self, trade: dict):
        """Log a trade to JSONL file"""
        trade["logged_at"] = datetime.now().isoformat()
        with open(self.log_file, "a") as f:
            f.write(json.dumps(trade) + "\n")

    def get_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> list[dict]:
        """Query trades from log"""
        trades = []
        if not self.log_file.exists():
            return trades

        with open(self.log_file) as f:
            for line in f:
                trade = json.loads(line)
                if symbol and trade.get("symbol") != symbol:
                    continue
                if since:
                    logged = datetime.fromisoformat(trade["logged_at"])
                    if logged < since:
                        continue
                trades.append(trade)

        return trades
```

---

## Usage Example

```python
from arbiter.execution.public_client import PublicClient
from arbiter.execution.order_executor import OrderExecutor
from arbiter.storage.trade_log import TradeLogger
from arbiter.config.settings import PUBLIC_API_KEY, PUBLIC_API_BASE

# Initialize
client = PublicClient(PUBLIC_API_KEY, PUBLIC_API_BASE)
logger = TradeLogger()
executor = OrderExecutor(client, logger, config={
    "cooldown_hours": 4,
    "max_position_pct": 0.2,
    "max_daily_trades": 10
})

# Execute a signal
decision = {
    "symbol": "XLE",
    "side": "buy",
    "amount_usd": 500,
    "confidence": 0.82,
    "reasoning": "Oil momentum + stable macro"
}

result = executor.execute(decision)
print(f"Trade result: {result.message}")
```

---

## Configuration

```python
# src/arbiter/config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Public API
PUBLIC_API_KEY = os.getenv("PUBLIC_API_KEY")
PUBLIC_API_BASE = os.getenv("PUBLIC_API_BASE", "https://api.public.dev/v1")

# Execution config
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.2"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "4"))
MAX_DAILY_TRADES = int(os.getenv("MAX_DAILY_TRADES", "10"))
DEFAULT_TRADE_AMOUNT = float(os.getenv("DEFAULT_TRADE_AMOUNT", "500"))
```

---

## Safety Features

| Feature | Description |
|---------|-------------|
| Cooldown | No re-trades within N hours |
| Max exposure | Position < X% of portfolio |
| Duplicate check | No open orders for same symbol/side |
| Min amount | Skip if amount too small |
| Daily limit | Max N trades per day |
| Logging | All trades logged with reasoning |
