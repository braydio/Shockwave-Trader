from __future__ import annotations

import unittest
from typing import Any

from arbiter.execution.public_client import PublicClient


class FakeResponse:
    def __init__(self, json_data: Any, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code
        self.content = b"" if json_data is None else b"json"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._json_data


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.requests: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("No fake responses left")
        return self.responses.pop(0)


class PublicClientTests(unittest.TestCase):
    def test_get_account_discovers_public_brokerage_account(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "accounts": [
                            {
                                "accountId": "ret-1",
                                "accountType": "RETIREMENT",
                                "brokerageAccountType": "IRA",
                                "optionsLevel": "NONE",
                                "tradePermissions": "BUY_ONLY",
                            },
                            {
                                "accountId": "brok-1",
                                "accountType": "BROKERAGE",
                                "brokerageAccountType": "MARGIN",
                                "optionsLevel": "LEVEL_2",
                                "tradePermissions": "BUY_AND_SELL",
                            },
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "accountId": "brok-1",
                        "buyingPower": {
                            "cashOnlyBuyingPower": "1200.50",
                            "buyingPower": "5200.50",
                        },
                        "equity": [
                            {"type": "CASH", "value": "1200.50"},
                            {"type": "LONG", "value": "4300.00"},
                        ],
                    }
                ),
            ]
        )
        client = PublicClient(access_token="token", session=session)

        account = client.get_account()

        self.assertEqual(account.account_id, "brok-1")
        self.assertEqual(account.cash, 1200.50)
        self.assertEqual(account.buying_power, 5200.50)
        self.assertEqual(account.equity, 5500.50)
        self.assertTrue(
            session.requests[0]["url"].endswith("/userapigateway/trading/account")
        )
        self.assertTrue(
            session.requests[1]["url"].endswith(
                "/userapigateway/trading/brok-1/portfolio/v2"
            )
        )

    def test_get_positions_normalizes_public_portfolio_payload(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "accountId": "brok-1",
                        "positions": [
                            {
                                "instrument": {"symbol": "AAPL", "type": "EQUITY"},
                                "quantity": "2.0",
                                "currentValue": "410.00",
                                "costBasis": {
                                    "totalCost": "390.00",
                                    "gainValue": "20.00",
                                },
                            }
                        ],
                    }
                )
            ]
        )
        client = PublicClient(access_token="token", session=session, account_id="brok-1")

        positions = client.get_positions()

        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].symbol, "AAPL")
        self.assertEqual(positions[0].qty, 2.0)
        self.assertEqual(positions[0].market_value, 410.0)
        self.assertEqual(positions[0].unrealized_pl, 20.0)
        self.assertEqual(positions[0].current_price, 205.0)

    def test_submit_order_uses_public_account_scoped_endpoint_and_payload(self) -> None:
        session = FakeSession(
            [
                FakeResponse({"orderId": "generated-id"}),
                FakeResponse(
                    {
                        "orderId": "generated-id",
                        "instrument": {"symbol": "MSFT", "type": "EQUITY"},
                        "side": "BUY",
                        "status": "SUBMITTED",
                        "quantity": "3",
                        "createdAt": "2026-03-20T12:00:00Z",
                    }
                ),
            ]
        )
        client = PublicClient(access_token="token", session=session, account_id="brok-1")

        order = client.submit_order("MSFT", 3.0, "buy", amount=150.0)

        create_request = session.requests[0]
        self.assertEqual(create_request["method"], "POST")
        self.assertTrue(
            create_request["url"].endswith("/userapigateway/trading/brok-1/order")
        )
        self.assertEqual(
            create_request["json"]["instrument"], {"symbol": "MSFT", "type": "EQUITY"}
        )
        self.assertEqual(create_request["json"]["orderSide"], "BUY")
        self.assertEqual(create_request["json"]["orderType"], "MARKET")
        self.assertEqual(create_request["json"]["expiration"], {"timeInForce": "DAY"})
        self.assertEqual(create_request["json"]["quantity"], "3")
        self.assertEqual(create_request["json"]["amount"], "150")
        self.assertEqual(order.id, "generated-id")
        self.assertEqual(order.symbol, "MSFT")
        self.assertEqual(order.side, "buy")
        self.assertEqual(order.status, "submitted")

    def test_submit_order_formats_fractional_sell_quantity(self) -> None:
        session = FakeSession(
            [
                FakeResponse(None, status_code=204),
                FakeResponse(
                    {
                        "orderId": "generated-id",
                        "instrument": {"symbol": "XLE", "type": "EQUITY"},
                        "side": "SELL",
                        "status": "SUBMITTED",
                        "quantity": "1.23456",
                        "createdAt": "2026-03-20T12:00:00Z",
                    }
                ),
            ]
        )
        client = PublicClient(access_token="token", session=session, account_id="brok-1")

        order = client.submit_order("XLE", 1.23456, "sell")

        create_request = session.requests[0]
        self.assertEqual(create_request["json"]["quantity"], "1.23456")
        self.assertNotIn("amount", create_request["json"])
        self.assertEqual(order.qty, 1.23456)

    def test_get_order_history_normalizes_account_history_entries(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "history": [
                            {
                                "activityId": "hist-1",
                                "instrument": {"symbol": "XLE", "type": "EQUITY"},
                                "orderSide": "SELL",
                                "filledQuantity": "2.5",
                                "eventType": "FILLED",
                                "timestamp": "2026-03-22T15:04:05Z",
                                "description": "Order filled",
                            }
                        ]
                    }
                )
            ]
        )
        client = PublicClient(access_token="token", session=session, account_id="brok-1")

        history = client.get_order_history(limit=10)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].id, "hist-1")
        self.assertEqual(history[0].symbol, "XLE")
        self.assertEqual(history[0].side, "sell")
        self.assertEqual(history[0].qty, 2.5)
        self.assertEqual(history[0].status, "filled")
        self.assertEqual(history[0].description, "Order filled")
        self.assertTrue(
            session.requests[0]["url"].endswith("/userapigateway/trading/brok-1/history")
        )


if __name__ == "__main__":
    unittest.main()
