"""Public Brokerage API client for trade execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
from uuid import uuid4

import requests

from arbiter.config.settings import (
    PUBLIC_ACCOUNT_ID,
    PUBLIC_API_ACCESS_TOKEN,
    PUBLIC_API_BASE,
    PUBLIC_API_SECRET_KEY,
)


@dataclass
class BrokerageAccount:
    """Normalized Public brokerage account metadata."""

    account_id: str
    account_type: str
    brokerage_account_type: str
    options_level: str
    trade_permissions: str


@dataclass
class Account:
    """Normalized account summary used by the CLI and execution layer."""

    account_id: str
    buying_power: float
    cash: float
    equity: float


@dataclass
class Position:
    """Normalized position view."""

    symbol: str
    qty: float
    market_value: float
    unrealized_pl: float
    current_price: float


@dataclass
class Order:
    """Normalized order view."""

    id: str
    symbol: str
    side: str
    qty: float
    status: str
    created_at: str


@dataclass
class OrderHistoryEntry:
    """Normalized historical order or account activity entry."""

    id: str
    symbol: str
    side: str
    qty: float
    status: str
    created_at: str
    description: str = ""


class PublicClient:
    """Client for the Public Individual API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        account_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = (base_url or PUBLIC_API_BASE).rstrip("/")
        self.access_token = access_token or PUBLIC_API_ACCESS_TOKEN
        self.secret_key = secret_key or PUBLIC_API_SECRET_KEY
        self.account_id = account_id or PUBLIC_ACCOUNT_ID
        self.session = session or requests.Session()
        self._bootstrap_auth()

    def _bootstrap_auth(self) -> None:
        """Populate the bearer token once, using secret-key exchange if needed."""
        if self.access_token:
            self.session.headers.update(
                {"Authorization": f"Bearer {self.access_token}"}
            )
            return

        if not self.secret_key:
            return

        token = self._create_personal_access_token()
        self.access_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _create_personal_access_token(self) -> str:
        """Exchange a Public secret key for a short-lived access token."""
        response = self.session.post(
            f"{self.base_url}/userapiauthservice/personal/access-tokens",
            json={
                "secret": self.secret_key,
                "validityInMinutes": 60,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("accessToken") or data.get("token")
        if not token:
            raise ValueError("Public auth response did not include an access token")
        return token

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make an authenticated HTTP request against the Public API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Content-Type", "application/json")
        response = self.session.request(
            method,
            url,
            headers=headers,
            timeout=kwargs.pop("timeout", 30),
            **kwargs,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def get_accounts(self) -> list[BrokerageAccount]:
        """Return all Public accounts available to the authenticated user."""
        data = self._request("GET", "/userapigateway/trading/account")
        accounts = data.get("accounts", []) if isinstance(data, dict) else []
        return [
            BrokerageAccount(
                account_id=account["accountId"],
                account_type=account.get("accountType", ""),
                brokerage_account_type=account.get("brokerageAccountType", ""),
                options_level=account.get("optionsLevel", ""),
                trade_permissions=account.get("tradePermissions", ""),
            )
            for account in accounts
        ]

    def _get_default_account_id(self) -> str:
        if self.account_id:
            return self.account_id

        accounts = self.get_accounts()
        if not accounts:
            raise ValueError("No Public accounts found for the authenticated user")

        for account in accounts:
            if account.account_type == "BROKERAGE":
                self.account_id = account.account_id
                return self.account_id

        self.account_id = accounts[0].account_id
        return self.account_id

    def get_portfolio(self, account_id: Optional[str] = None) -> dict[str, Any]:
        """Return the raw Public portfolio payload for an account."""
        resolved_account_id = account_id or self._get_default_account_id()
        data = self._request(
            "GET",
            f"/userapigateway/trading/{resolved_account_id}/portfolio/v2",
        )
        return data if isinstance(data, dict) else {}

    def get_account(self, account_id: Optional[str] = None) -> Account:
        """Return a normalized account summary from Public's portfolio response."""
        portfolio = self.get_portfolio(account_id)
        resolved_account_id = (
            portfolio.get("accountId") or account_id or self._get_default_account_id()
        )
        buying_power = portfolio.get("buyingPower", {})
        equity_buckets = portfolio.get("equity", [])

        total_equity = sum(
            self._to_float(bucket.get("value"))
            for bucket in equity_buckets
            if isinstance(bucket, dict)
        )
        if not total_equity:
            total_equity = self._to_float(portfolio.get("portfolioValue"))

        return Account(
            account_id=resolved_account_id,
            buying_power=self._to_float(buying_power.get("buyingPower")),
            cash=self._to_float(buying_power.get("cashOnlyBuyingPower")),
            equity=total_equity,
        )

    def get_positions(self, account_id: Optional[str] = None) -> list[Position]:
        """Return normalized positions from Public's portfolio response."""
        portfolio = self.get_portfolio(account_id)
        positions = portfolio.get("positions", [])
        normalized: list[Position] = []

        for position in positions:
            instrument = position.get("instrument", {})
            quantity = self._to_float(position.get("quantity"))
            market_value = self._to_float(position.get("currentValue"))
            cost_basis = position.get("costBasis") or {}
            total_cost = (
                self._to_float(cost_basis.get("totalCost")) if cost_basis else 0.0
            )
            current_price = market_value / quantity if quantity else 0.0

            normalized.append(
                Position(
                    symbol=instrument.get("symbol", ""),
                    qty=quantity,
                    market_value=market_value,
                    unrealized_pl=self._to_float(cost_basis.get("gainValue"))
                    or market_value - total_cost
                    if cost_basis
                    else 0.0,
                    current_price=current_price,
                )
            )

        return normalized

    def get_position(
        self, symbol: str, account_id: Optional[str] = None
    ) -> Optional[Position]:
        """Return a single position by symbol."""
        target = symbol.upper()
        for position in self.get_positions(account_id):
            if position.symbol.upper() == target:
                return position
        return None

    def get_quote(
        self, symbol: str, account_id: Optional[str] = None
    ) -> Optional[float]:
        """Return the latest Public quote for a symbol when marketdata scope is enabled."""
        resolved_account_id = account_id or self._get_default_account_id()
        data = self._request(
            "POST",
            f"/userapigateway/marketdata/{resolved_account_id}/quotes",
            json={"instruments": [{"symbol": symbol.upper(), "type": "EQUITY"}]},
        )
        quotes = data.get("quotes", []) if isinstance(data, dict) else []
        if not quotes:
            return None
        quote = quotes[0]
        return self._to_float(quote.get("last") or quote.get("ask") or quote.get("bid"))

    def get_price(
        self, symbol: str, account_id: Optional[str] = None
    ) -> Optional[float]:
        """Return the current market price for a symbol."""
        quote_price = self.get_quote(symbol, account_id)
        if quote_price:
            return quote_price

        position = self.get_position(symbol, account_id)
        if position:
            return position.current_price

        return None

    def get_order(self, order_id: str, account_id: Optional[str] = None) -> Order:
        """Return a normalized order from Public's order endpoint."""
        resolved_account_id = account_id or self._get_default_account_id()
        data = self._request(
            "GET",
            f"/userapigateway/trading/{resolved_account_id}/order/{order_id}",
        )
        instrument = data.get("instrument", {}) if isinstance(data, dict) else {}
        return Order(
            id=data.get("orderId", order_id),
            symbol=instrument.get("symbol", ""),
            side=str(data.get("side", "")).lower(),
            qty=self._to_float(data.get("quantity")),
            status=str(data.get("status", "")).lower(),
            created_at=data.get("createdAt", ""),
        )

    def get_orders(
        self, status: Optional[str] = None, account_id: Optional[str] = None
    ) -> list[Order]:
        """Return orders surfaced in the Public portfolio snapshot, optionally filtered."""
        portfolio = self.get_portfolio(account_id)
        orders = portfolio.get("orders", [])
        normalized: list[Order] = []
        requested_status = status.lower() if status else None

        for order in orders:
            instrument = order.get("instrument", {})
            normalized_order = Order(
                id=order.get("orderId", ""),
                symbol=instrument.get("symbol", ""),
                side=str(order.get("side", "")).lower(),
                qty=self._to_float(order.get("quantity")),
                status=str(order.get("status", "")).lower(),
                created_at=order.get("createdAt", ""),
            )
            if requested_status and normalized_order.status != requested_status:
                continue
            normalized.append(normalized_order)

        return normalized

    def get_order_history(
        self, limit: int = 50, account_id: Optional[str] = None
    ) -> list[OrderHistoryEntry]:
        """Return recent historical order activity from Public account history."""
        resolved_account_id = account_id or self._get_default_account_id()
        data = self._request(
            "GET",
            f"/userapigateway/trading/{resolved_account_id}/history",
        )

        raw_items: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for key in ("history", "items", "entries", "activities", "orders"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_items = [item for item in value if isinstance(item, dict)]
                    if raw_items:
                        break
        elif isinstance(data, list):
            raw_items = [item for item in data if isinstance(item, dict)]

        entries = [self._normalize_history_entry(item) for item in raw_items]
        entries = [entry for entry in entries if entry is not None]
        entries.sort(key=lambda entry: entry.created_at or "", reverse=True)
        if limit > 0:
            entries = entries[:limit]
        return entries

    def submit_order(
        self,
        symbol: str,
        qty: Optional[float],
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        limit_price: Optional[float] = None,
        amount: Optional[float] = None,
        account_id: Optional[str] = None,
    ) -> Order:
        """Submit an equity order through Public's account-scoped order endpoint."""
        resolved_account_id = account_id or self._get_default_account_id()
        order_id = str(uuid4())
        payload: dict[str, Any] = {
            "orderId": order_id,
            "instrument": {"symbol": symbol.upper(), "type": "EQUITY"},
            "orderSide": side.upper(),
            "orderType": order_type.upper(),
            "expiration": {"timeInForce": time_in_force.upper()},
        }
        if qty is not None and qty > 0:
            payload["quantity"] = self._format_decimal(qty)
        if amount is not None and amount > 0:
            payload["amount"] = self._format_decimal(amount)
        if limit_price is not None:
            payload["limitPrice"] = f"{limit_price:.2f}"

        self._request(
            "POST",
            f"/userapigateway/trading/{resolved_account_id}/order",
            json=payload,
        )

        try:
            return self.get_order(order_id, resolved_account_id)
        except requests.HTTPError:
            return Order(
                id=order_id,
                symbol=symbol.upper(),
                side=side.lower(),
                qty=self._to_float(qty),
                status="submitted",
                created_at="",
            )

    def cancel_order(self, order_id: str, account_id: Optional[str] = None) -> bool:
        """Cancel an open order."""
        resolved_account_id = account_id or self._get_default_account_id()
        try:
            self._request(
                "DELETE",
                f"/userapigateway/trading/{resolved_account_id}/order/{order_id}",
            )
            return True
        except requests.HTTPError:
            return False

    def _normalize_history_entry(
        self, item: dict[str, Any]
    ) -> Optional[OrderHistoryEntry]:
        instrument = item.get("instrument") if isinstance(item.get("instrument"), dict) else {}
        symbol = (
            instrument.get("symbol")
            or item.get("symbol")
            or item.get("ticker")
            or ""
        )
        side = (
            item.get("side")
            or item.get("orderSide")
            or item.get("transactionSide")
            or ""
        )
        status = item.get("status") or item.get("eventType") or item.get("type") or ""
        quantity = (
            item.get("quantity")
            or item.get("filledQuantity")
            or item.get("orderQuantity")
            or 0
        )
        created_at = (
            item.get("createdAt")
            or item.get("timestamp")
            or item.get("submittedAt")
            or item.get("updatedAt")
            or ""
        )
        entry_id = (
            item.get("orderId")
            or item.get("id")
            or item.get("activityId")
            or ""
        )
        description = (
            item.get("description")
            or item.get("title")
            or item.get("summary")
            or ""
        )

        if not any([entry_id, symbol, description, created_at]):
            return None

        return OrderHistoryEntry(
            id=str(entry_id),
            symbol=str(symbol),
            side=str(side).lower(),
            qty=self._to_float(quantity),
            status=str(status).lower(),
            created_at=str(created_at),
            description=str(description),
        )

    @staticmethod
    def _format_decimal(value: float) -> str:
        text = f"{float(value):.5f}"
        text = text.rstrip("0").rstrip(".")
        return text or "0"
