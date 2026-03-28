# Arbiter Demo Transcript

This document is a supporting narration guide for the Arbiter demo recording.
It is written to match the current `demo.sh` flow and explain what the viewer is seeing.

## Short Intro

Hi, this is Arbiter, my event-driven trading system built for the Public Brokerage API competition.

The idea behind Arbiter is simple: collect real-world signals, detect what is actually new, confirm that the market agrees, and then route execution through either Public Brokerage or a local paper-trading ledger.

For this demo, I am running in dry-run mode with the local paper backend enabled. That means I can show the full decision and execution flow without placing a live broker order.

## Product Framing

Arbiter is designed as an ingestion-to-execution pipeline:

1. Collect market, macro, and event data.
2. Normalize and compare that data with prior state.
3. Score it with a strategy.
4. Produce a trade decision.
5. Route that decision to either Public Brokerage or a local paper account.

The strategy currently demonstrated is Energy Shock Confirmation.
The thesis is that when geopolitical or supply-side stress increases energy risk, and market price action confirms it, Arbiter can rotate into liquid energy exposure.

## Demo Walkthrough

### Opening

What you are seeing first is the automated demo script starting up the environment and running a series of fast strategy cycles.

This is useful because it shows the system as an actual loop, not just a static interface.
Each cycle pulls fresh data, recomputes the signal, and checks whether current conditions justify a trade.

### Fast Cycles

During these fast cycles, Arbiter is:

- pulling market data for instruments like `XLE`, `USO`, `SPY`, and `VIXY`
- collecting supporting event context from macro and news sources
- running delta logic to separate genuinely new information from repeated noise
- scoring the trade setup with the strategy engine
- optionally sending the resulting trade hypothesis to OpenAI for a fast adversarial review before execution

If OpenAI is configured, the demo now automatically packages:

- the current trade thesis
- live market context
- signal confidence and regime data
- the available risk budget based on equity and buying power

That review is not making the trade decision by itself.
It is acting as a second-pass reasoning layer that can summarize support, identify risks, and suggest invalidation conditions.

### Interactive CLI

After the automated cycles complete, the demo moves into the interactive CLI.
This section is meant to show that the same system is inspectable and usable by an operator in real time.

### Market Data

The first screen shows market data.
This gives a quick snapshot of the symbols the strategy cares about and whether price action is confirming or contradicting the narrative signal.

For this strategy, market confirmation matters.
The system is not trying to trade headlines in isolation.
It wants both a real-world catalyst and a market response.

### Account Info

Next is account information.
Because the demo is using the local paper backend, the balances shown here are coming from the local simulated account state rather than a live brokerage account.

That paper account starts from a configurable amount in `.env`, which makes it easy to test the exact same system under different capital assumptions.

### Open Positions

Then we show open positions.
This proves Arbiter is maintaining persistent position state across cycles rather than treating every run as stateless.

That matters because exits, risk management, cooldowns, and performance tracking all depend on durable state.

### Submit Trade

Next, the demo submits a trade from the CLI.
This is useful because it validates the execution path independently of the automated strategy loop.

At this point Arbiter:

- validates the order
- checks cooldowns
- checks risk limits
- sizes the order
- supports fractional-share handling
- routes the order into the selected backend

In paper mode, that means the order is recorded locally and reflected immediately in the simulated account state.
In live mode, the same flow targets the Public Brokerage integration.

### Open Orders

The open orders screen shows that submitted orders are tracked as normalized order objects.
This creates a consistent interface no matter which backend is active.

That normalization matters because it keeps the rest of the application from being tightly coupled to a single broker response format.

### Order History

Next is order history.
This view is important because it shows Arbiter is not only able to submit trades, but also inspect historical order activity.

With Public Brokerage, this pulls from the broker-side account history endpoint and normalizes the result.
With paper trading, it reads from the persisted local ledger.

That means the operator experience stays coherent across both live and simulated environments.

### Trade Hypothesis Review

If OpenAI is configured, the last major feature shown in the CLI is trade hypothesis review.

This is where Arbiter sends a structured trade package to the OpenAI API.
The prompt includes:

- symbol and side
- the trade thesis
- current market context
- requested notional size
- available budget and buying power
- risk notes from the live strategy signal

The goal here is not to let a language model blindly decide whether to trade.
The goal is to pressure-test the hypothesis, surface the strongest support, highlight the main failure modes, and create a cleaner operator-facing explanation.

For a competition demo, this is valuable because it shows the system is not just automated, but inspectable and explainable.

## Why the Local Paper Layer Matters

Public Brokerage does not currently expose a native paper-trading environment.
Because of that, I implemented a local paper backend that mirrors the execution flow closely enough for development, testing, and demonstration.

This gives Arbiter:

- a configurable starting balance
- persistent simulated account state
- local positions and order history
- fast dry-run and demo support without broker risk

That paper layer lets me design against the real Public integration while still iterating safely.

## Why This Matters for the Competition

The point of this project is not only to place trades.
It is to show a complete operator workflow around the Public Brokerage API:

- signal generation
- risk controls
- broker-aware execution
- order history and inspection
- explainability
- safe local simulation when live broker testing is not appropriate

That combination is what makes Arbiter a practical trading application instead of just a one-off API demo.

## Closing

To summarize, Arbiter is an event-driven trading framework that:

- turns live information into structured signals
- confirms those signals against market behavior
- enforces sizing and exposure controls
- executes through Public Brokerage or a local paper ledger
- tracks orders and positions over time
- and can optionally send its trade hypothesis through OpenAI for an additional review layer

This demo is meant to show that the core pieces are already working together as one coherent system.

## Optional Short Closing Version

Arbiter is my event-driven trading system for the Public Brokerage competition.
It ingests macro, news, and market data, scores a strategy, applies risk controls, and routes execution through either Public Brokerage or a local paper account.
For this demo, I’m showing the full operator flow: market context, account state, order submission, order history, and an optional OpenAI-powered trade review layer that pressure-tests each thesis before execution.
