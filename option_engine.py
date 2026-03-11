"""
Option Strategy Engine
----------------------

This module selects option spreads based on option chain data
using delta-based strike selection.

Supported Strategies:
- Bull Put Spread
- Bear Call Spread
- Iron Condor

Safety:
- Never allow naked option selling
- Always include hedge leg
"""

import math


# -----------------------------
# Utility Functions
# -----------------------------

def find_closest_delta(options, target_delta):
    """
    Return option whose delta is closest to target.
    """

    if not options:
        return None

    return min(
        options,
        key=lambda x: abs(x.get("delta", 0) - target_delta)
    )


def filter_calls(option_chain):

    return [
        o for o in option_chain
        if o.get("type") == "CE"
    ]


def filter_puts(option_chain):

    return [
        o for o in option_chain
        if o.get("type") == "PE"
    ]


# -----------------------------
# Bull Put Spread
# -----------------------------

def build_bull_put_spread(option_chain, min_width=100):

    puts = filter_puts(option_chain)

    if not puts:
        return None

    sell_put = find_closest_delta(puts, -0.25)

    if sell_put is None:
        return None

    hedge_candidates = [
        p for p in puts
        if p["strike"] < sell_put["strike"]
        and abs(p["strike"] - sell_put["strike"]) >= min_width
    ]

    buy_put = find_closest_delta(hedge_candidates, -0.10)

    if buy_put is None:
        return None

    return {
        "strategy": "Bull Put Spread",
        "sell_leg": sell_put,
        "buy_leg": buy_put,
        "width": abs(sell_put["strike"] - buy_put["strike"])
    }


# -----------------------------
# Bear Call Spread
# -----------------------------

def build_bear_call_spread(option_chain, min_width=100):

    calls = filter_calls(option_chain)

    if not calls:
        return None

    sell_call = find_closest_delta(calls, 0.25)

    if sell_call is None:
        return None

    hedge_candidates = [
        c for c in calls
        if c["strike"] > sell_call["strike"]
        and abs(c["strike"] - sell_call["strike"]) >= min_width
    ]

    buy_call = find_closest_delta(hedge_candidates, 0.10)

    if buy_call is None:
        return None

    return {
        "strategy": "Bear Call Spread",
        "sell_leg": sell_call,
        "buy_leg": buy_call,
        "width": abs(sell_call["strike"] - buy_call["strike"])
    }


# -----------------------------
# Iron Condor
# -----------------------------

def build_iron_condor(option_chain, min_width=100):

    calls = filter_calls(option_chain)
    puts = filter_puts(option_chain)

    if not calls or not puts:
        return None

    sell_call = find_closest_delta(calls, 0.20)

    call_hedges = [
        c for c in calls
        if c["strike"] > sell_call["strike"]
        and abs(c["strike"] - sell_call["strike"]) >= min_width
    ]

    buy_call = find_closest_delta(call_hedges, 0.05)

    sell_put = find_closest_delta(puts, -0.20)

    put_hedges = [
        p for p in puts
        if p["strike"] < sell_put["strike"]
        and abs(p["strike"] - sell_put["strike"]) >= min_width
    ]

    buy_put = find_closest_delta(put_hedges, -0.05)

    if None in (sell_call, buy_call, sell_put, buy_put):
        return None

    return {
        "strategy": "Iron Condor",
        "sell_call": sell_call,
        "buy_call": buy_call,
        "sell_put": sell_put,
        "buy_put": buy_put,
        "call_width": abs(sell_call["strike"] - buy_call["strike"]),
        "put_width": abs(sell_put["strike"] - buy_put["strike"])
    }


# -----------------------------
# Strategy Router
# -----------------------------

def build_strategy(option_chain, market_trend):

    """
    Select strategy based on market direction
    """

    if market_trend == "BULLISH":

        return build_bull_put_spread(option_chain)

    elif market_trend == "BEARISH":

        return build_bear_call_spread(option_chain)

    else:

        return build_iron_condor(option_chain)


# -----------------------------
# Strategy Formatter
# -----------------------------

def format_strategy(strategy):

    if strategy is None:
        return "No valid spread found"

    name = strategy["strategy"]

    if name == "Bull Put Spread":

        sell = strategy["sell_leg"]
        buy = strategy["buy_leg"]

        return (
            f"SELL {sell['strike']} PE (Δ {sell['delta']}) | "
            f"BUY {buy['strike']} PE (Δ {buy['delta']})"
        )

    elif name == "Bear Call Spread":

        sell = strategy["sell_leg"]
        buy = strategy["buy_leg"]

        return (
            f"SELL {sell['strike']} CE (Δ {sell['delta']}) | "
            f"BUY {buy['strike']} CE (Δ {buy['delta']})"
        )

    elif name == "Iron Condor":

        sc = strategy["sell_call"]
        bc = strategy["buy_call"]
        sp = strategy["sell_put"]
        bp = strategy["buy_put"]

        return (
            f"SELL {sc['strike']} CE | BUY {bc['strike']} CE | "
            f"SELL {sp['strike']} PE | BUY {bp['strike']} PE"
        )

    return "Unknown strategy"