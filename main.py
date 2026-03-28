#!/usr/bin/env python3
"""Arbiter CLI - Simple command interface."""

import asyncio
import sys
from pathlib import Path

# Add this repo's src directory to the import path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from rich.console import Console
from rich.table import Table

from arbiter.collectors.yfinance_collector import YFinanceCollector
from arbiter.config.settings import (
    DEFAULT_TRADE_AMOUNT,
    EXECUTION_BACKEND,
)
from arbiter.execution.client import create_execution_client
from arbiter.execution.order_executor import OrderExecutor, TradeDecision
from arbiter.storage.trade_log import TradeLogger

console = Console()


def get_execution_client():
    """Create the configured execution backend for interactive use."""
    client = create_execution_client()
    if client is None:
        raise RuntimeError(
            "No execution backend is configured. Set EXECUTION_BACKEND or broker credentials."
        )
    return client


async def show_market_data():
    """Display current market data."""
    console.print("\n[bold cyan]Fetching Market Data...[/bold cyan]")

    collector = YFinanceCollector()
    raw = await collector.fetch()

    if not raw:
        console.print("[yellow]No data received[/yellow]")
        return

    table = Table(title="Market Overview", style="bold green")
    table.add_column("Symbol", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Change %", justify="right")
    table.add_column("Direction", justify="center")

    for symbol, info in raw.items():
        change = info["change_pct"]
        color = "green" if change > 0 else "red" if change < 0 else "yellow"
        direction = "▲" if change > 0 else "▼" if change < 0 else "―"

        table.add_row(
            symbol,
            f"${info['price']:.2f}",
            f"{change:+.2f}%",
            f"[{color}]{direction}[/{color}]",
        )

    console.print(table)


def show_account():
    """Display account info."""
    console.print("\n[bold cyan]Fetching Account...[/bold cyan]")

    try:
        client = get_execution_client()
        account = client.get_account()

        table = Table(title=f"{EXECUTION_BACKEND.title()} Account", style="bold blue")
        table.add_column("Field", style="cyan")
        table.add_column("Value", justify="right", style="yellow")

        table.add_row("Account ID", account.account_id)
        table.add_row("Cash", f"${account.cash:,.2f}")
        table.add_row("Buying Power", f"${account.buying_power:,.2f}")
        table.add_row("Equity", f"${account.equity:,.2f}")

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def show_positions():
    """Display open positions."""
    try:
        client = get_execution_client()
        positions = client.get_positions()

        if not positions:
            console.print("[yellow]No open positions[/yellow]")
            return

        table = Table(title="Open Positions", style="bold green")
        table.add_column("Symbol", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("P/L", justify="right")

        for pos in positions:
            pl_color = (
                "green"
                if pos.unrealized_pl > 0
                else "red"
                if pos.unrealized_pl < 0
                else "yellow"
            )
            table.add_row(
                pos.symbol,
                f"{pos.qty:g}",
                f"${pos.market_value:,.2f}",
                f"[{pl_color}]${pos.unrealized_pl:+,.2f}[/{pl_color}]",
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


def submit_trade():
    """Submit a trade through Arbiter's configured executor."""
    symbol = console.input("\n[bold cyan]Symbol: [/bold cyan]").strip().upper()
    side = console.input("[bold cyan]Side (buy/sell): [/bold cyan]").strip().lower()
    amount_raw = console.input(
        "[bold cyan]Dollar amount (leave blank to use default): [/bold cyan]"
    ).strip()

    if side not in {"buy", "sell"}:
        console.print("[red]Invalid side. Use buy or sell.[/red]")
        return

    amount_usd = 0.0
    if amount_raw:
        try:
            amount_usd = float(amount_raw)
        except ValueError:
            console.print("[red]Invalid dollar amount[/red]")
            return

    try:
        executor = OrderExecutor()
        decision = TradeDecision(
            symbol=symbol,
            side=side,
            amount_usd=amount_usd or DEFAULT_TRADE_AMOUNT,
            confidence=1.0,
            reasoning="Manual CLI trade submission",
        )
        result = executor.execute(decision)
        console.print(f"[green]{result.message}[/green]")
        if result.order:
            console.print(f"[dim]Order ID: {result.order.id} | Status: {result.order.status}[/dim]")
    except Exception as exc:
        console.print(f"[red]Trade failed: {exc}[/red]")


def show_orders():
    """Display recent open or recently filled orders."""
    try:
        client = get_execution_client()
        orders = client.get_orders(status="submitted") or client.get_orders(status="open")
        if not orders:
            orders = client.get_orders(status="filled")
        if not orders:
            console.print("[yellow]No surfaced orders[/yellow]")
            return

        table = Table(title="Orders", style="bold yellow")
        table.add_column("ID")
        table.add_column("Symbol", style="cyan")
        table.add_column("Side")
        table.add_column("Qty", justify="right")
        table.add_column("Status")

        for order in orders:
            table.add_row(
                order.id[:8],
                order.symbol,
                order.side,
                f"{order.qty:g}",
                order.status,
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


def show_order_history():
    """Display recent order history, falling back to local trade log if needed."""
    try:
        client = get_execution_client()
        history = []
        if hasattr(client, "get_order_history"):
            history = client.get_order_history(limit=20)

        if history:
            table = Table(title="Order History", style="bold magenta")
            table.add_column("When")
            table.add_column("Symbol", style="cyan")
            table.add_column("Side")
            table.add_column("Qty", justify="right")
            table.add_column("Status")
            table.add_column("Note")

            for entry in history:
                table.add_row(
                    (entry.created_at or "")[:19],
                    entry.symbol or "-",
                    entry.side or "-",
                    f"{entry.qty:g}" if entry.qty else "-",
                    entry.status or "-",
                    entry.description or "-",
                )
            console.print(table)
            return

        entries = TradeLogger().read_trades(limit=20)
        if not entries:
            console.print("[yellow]No order history found[/yellow]")
            return

        table = Table(title="Local Trade Log", style="bold magenta")
        table.add_column("When")
        table.add_column("Symbol", style="cyan")
        table.add_column("Side")
        table.add_column("Qty", justify="right")
        table.add_column("Order ID")

        for entry in reversed(entries):
            decision = entry.get("decision", {})
            order = entry.get("order", {})
            table.add_row(
                entry.get("timestamp", "")[:19],
                decision.get("symbol", "-"),
                decision.get("side", "-"),
                str(decision.get("qty", "-")),
                str(order.get("id") or order.get("orderId") or "-"),
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")


def print_menu():
    """Display main menu."""
    console.print("\n[bold green]Arbiter CLI[/bold green]")
    console.print("=" * 40)
    console.print("[1] Market Data (YFinance)")
    console.print("[2] Account Info")
    console.print("[3] Open Positions")
    console.print("[4] Submit Trade")
    console.print("[5] Open Orders")
    console.print("[6] Order History")
    console.print("[0] Exit")
    console.print()


def main():
    """Main CLI loop."""
    console.print("[bold green]Arbiter CLI[/bold green]")
    console.print("Ingestion → Signal → Execution\n")

    while True:
        print_menu()
        choice = console.input("[bold cyan]Select option: [/bold cyan]").strip()

        if choice == "1":
            asyncio.run(show_market_data())
        elif choice == "2":
            show_account()
        elif choice == "3":
            show_positions()
        elif choice == "4":
            submit_trade()
        elif choice == "5":
            show_orders()
        elif choice == "6":
            show_order_history()
        elif choice == "0":
            console.print("[bold red]Goodbye![/bold red]")
            sys.exit(0)
        else:
            console.print("[yellow]Invalid option[/yellow]")

        console.input("\n[dim]Press Enter to continue...[/dim]")


if __name__ == "__main__":
    main()
