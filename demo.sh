#!/bin/bash
# Arbiter Demo Script
# Run this to demonstrate the trading system

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              ARBITER TRADING BOT DEMO                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "This demo shows Arbiter detecting energy shock signals"
echo "and executing trades on Public API."
echo ""
echo "⚠️  Running in DRY-RUN mode (no real trades)"
echo ""

cd "$(dirname "$0")"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run:"
    echo "   python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "Starting Arbiter..."
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run the daemon
PYTHONPATH=src venv/bin/python3 -m arbiter.scheduler.daemon --dry-run --cycle 60
