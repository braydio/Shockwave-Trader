#!/bin/bash
# Arbiter Demo Script
# Run this to demonstrate the trading system
#
# Usage:
#   ./demo.sh           Run 3 fast cycles, then auto-demo CLI menu

set -e

cd "$(dirname "$0")"

PROMPT_PAUSE=1
RESPONSE_PAUSE=5
TITLE_PAUSE=4
FINAL_PAUSE=6

# Resolve virtualenv path
if [ -d ".venv" ]; then
    VENV_DIR=".venv"
elif [ -d "venv" ]; then
    VENV_DIR="venv"
else
    echo "❌ Virtual environment not found. Run:"
    echo "   python3 -m venv .venv && .venv/bin/pip install -e .[dev]"
    exit 1
fi

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              ARBITER TRADING BOT DEMO                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "⚠️  Running in DRY-RUN mode (no real trades)"
echo ""
echo "Running 4 fast cycles (3s each)..."
echo ""
sleep $TITLE_PAUSE

if [ -n "${OPENAI_API_KEY:-}" ]; then
    DEMO_OPENAI_ENV="OPENAI_ADVISOR_ENABLED=${OPENAI_ADVISOR_ENABLED:-true}"
else
    DEMO_OPENAI_ENV=""
fi

# Run daemon for 4 cycles (12 seconds total)
env PYTHONPATH=src $DEMO_OPENAI_ENV $VENV_DIR/bin/python3 -c "
import asyncio
import sys
sys.path.insert(0, 'src')
from arbiter.scheduler.daemon import ArbiterDaemon
from arbiter.execution.client import ExecutionBackend

async def run():
    daemon = ArbiterDaemon(cycle_seconds=3, dry_run=True, backend=ExecutionBackend.PAPER)
    await daemon.initialize()
    print('\n[yellow]⚡ Running 4 fast cycles...[/yellow]\n')
    for i in range(4):
        await daemon.run_cycle()
        await asyncio.sleep(0.5)
    print('\n[green]✓ Demo cycles complete![/green]\n')
    from arbiter.collectors.telegram_collector import TelegramCollector
    await TelegramCollector.close()

asyncio.run(run())
"

echo ""
echo "Running interactive CLI demo..."
echo ""

if [ -n "${OPENAI_API_KEY:-}" ]; then
    HYPOTHESIS_STEP="7"
else
    HYPOTHESIS_STEP=""
fi

# Auto-run CLI menu options with delays
{
    echo "1"  # Market Data
    sleep $RESPONSE_PAUSE
    echo ""
    sleep $PROMPT_PAUSE
    echo "2"  # Account Info
    sleep $RESPONSE_PAUSE
    echo ""
    sleep $PROMPT_PAUSE
    echo "3"  # Open Positions
    sleep $RESPONSE_PAUSE
    echo ""
    sleep $PROMPT_PAUSE
    echo "4"  # Submit Trade
    sleep $PROMPT_PAUSE
    echo "NVDA"    # Symbol
    sleep $PROMPT_PAUSE
    echo "buy"     # Side
    sleep $PROMPT_PAUSE
    echo "1000"    # Amount
    sleep $RESPONSE_PAUSE
    echo ""
    sleep $PROMPT_PAUSE
    echo "5"  # Open Orders
    sleep $RESPONSE_PAUSE
    echo ""
    sleep $PROMPT_PAUSE
    echo "6"  # Order History
    sleep $RESPONSE_PAUSE
    echo ""
    sleep $PROMPT_PAUSE
    if [ -n "$HYPOTHESIS_STEP" ]; then
        echo "7"  # Trade Hypothesis Review
        sleep $PROMPT_PAUSE
        echo "XLE"
        sleep $PROMPT_PAUSE
        echo "buy"
        sleep $PROMPT_PAUSE
        echo "Energy supply disruption plus relative strength in XLE versus SPY supports a tactical long."
        sleep $PROMPT_PAUSE
        echo "XLE up 1.4 percent today, USO confirming, VIX contained."
        sleep $PROMPT_PAUSE
        echo "\$1000 notional"
        sleep $PROMPT_PAUSE
        echo "Invalidation on fading event pressure or XLE losing relative strength."
        sleep $RESPONSE_PAUSE
        echo ""
        sleep $PROMPT_PAUSE
    fi
    sleep $FINAL_PAUSE
    echo "0"  # Exit
} | env PYTHONPATH=src $DEMO_OPENAI_ENV $VENV_DIR/bin/python3 main.py
