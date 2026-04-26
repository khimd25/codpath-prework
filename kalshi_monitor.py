#!/usr/bin/env python3
"""
Kalshi Price Alert Monitor
Polls Kalshi prediction markets and sends iOS push notifications via ntfy.sh
when a market's YES price moves by a configured percentage-point threshold.

Setup:
  1. pip install -r requirements.txt
  2. Edit config.json with your market tickers and alert thresholds
  3. Install the ntfy app on your iPhone and subscribe to your topic
  4. python kalshi_monitor.py

Kalshi API docs: https://trading-api.kalshi.com/trade-api/v2/docs
ntfy docs:       https://ntfy.sh/docs/
"""

import json
import os
import sys
import time
import logging
import argparse
from datetime import datetime
from typing import Optional

import requests

CONFIG_FILE = "config.json"
STATE_FILE = ".alert_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Kalshi API
# ---------------------------------------------------------------------------

KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"


def fetch_market(ticker: str, api_key: Optional[str] = None) -> dict:
    """Return raw market data for a single ticker."""
    url = f"{KALSHI_BASE}/markets/{ticker}"
    headers = {"accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get("market", {})


def get_yes_price(market: dict) -> Optional[float]:
    """
    Return the current YES mid-price as a percentage (0-100).
    Kalshi prices are in cents (0-100), so no conversion needed.
    Falls back to last_price if bid/ask aren't available.
    """
    bid = market.get("yes_bid")
    ask = market.get("yes_ask")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    last = market.get("last_price")
    if last is not None:
        return float(last)
    return None


# ---------------------------------------------------------------------------
# ntfy.sh push notifications
# ---------------------------------------------------------------------------

def send_notification(
    topic: str,
    title: str,
    message: str,
    priority: str = "high",
    tags: list[str] | None = None,
):
    """
    POST a push notification to ntfy.sh.
    The ntfy iOS app (https://apps.apple.com/app/ntfy/id1625396347)
    receives it instantly when subscribed to the same topic.
    """
    url = f"https://ntfy.sh/{topic}"
    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": ",".join(tags or ["bell"]),
    }
    try:
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        resp.raise_for_status()
        log.info("Notification sent → %s | %s", title, message)
    except requests.RequestException as exc:
        log.warning("Failed to send notification: %s", exc)


# ---------------------------------------------------------------------------
# State persistence (track baseline prices between runs)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Alert logic
# ---------------------------------------------------------------------------

def check_market(market_cfg: dict, state: dict, ntfy_topic: str, api_key: Optional[str]):
    ticker = market_cfg["ticker"]
    name = market_cfg.get("name", ticker)
    threshold = float(market_cfg.get("alert_threshold_percent", 3.0))
    direction = market_cfg.get("direction", "both").lower()  # "up", "down", "both"

    try:
        market = fetch_market(ticker, api_key)
    except requests.HTTPError as exc:
        log.error("HTTP error fetching %s: %s", ticker, exc)
        return
    except requests.RequestException as exc:
        log.error("Network error fetching %s: %s", ticker, exc)
        return

    current = get_yes_price(market)
    if current is None:
        log.warning("No price available for %s", ticker)
        return

    baseline = state.get(ticker, {}).get("baseline_price")
    last_alerted = state.get(ticker, {}).get("last_alerted_price")

    # Use last_alerted as the comparison base when available (so alerts don't repeat)
    compare_to = last_alerted if last_alerted is not None else baseline

    if compare_to is None:
        # First run — just record the baseline, no alert yet
        state[ticker] = {
            "baseline_price": current,
            "last_alerted_price": None,
            "last_checked": datetime.utcnow().isoformat(),
        }
        log.info("%s  baseline set → %.1f%%", ticker, current)
        return

    delta = current - compare_to
    abs_delta = abs(delta)

    log.info(
        "%s  current=%.1f%%  compare_to=%.1f%%  delta=%+.1f pp",
        ticker, current, compare_to, delta,
    )

    should_alert = (
        abs_delta >= threshold
        and (
            direction == "both"
            or (direction == "up" and delta > 0)
            or (direction == "down" and delta < 0)
        )
    )

    if should_alert:
        direction_word = "up" if delta > 0 else "down"
        emoji = "📈" if delta > 0 else "📉"
        title = f"{emoji} Kalshi Alert: {name}"
        msg = (
            f"{name} moved {direction_word} {abs_delta:.1f} percentage points\n"
            f"Previous: {compare_to:.1f}%  →  Now: {current:.1f}%"
        )
        tags = ["chart_with_upwards_trend" if delta > 0 else "chart_with_downwards_trend"]
        send_notification(ntfy_topic, title, msg, tags=tags)

        state[ticker] = {
            "baseline_price": state.get(ticker, {}).get("baseline_price", compare_to),
            "last_alerted_price": current,
            "last_checked": datetime.utcnow().isoformat(),
        }
    else:
        if ticker not in state:
            state[ticker] = {}
        state[ticker]["last_checked"] = datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def run(config: dict, once: bool = False):
    ntfy_topic = config.get("ntfy_topic", "kalshi-alerts")
    api_key = config.get("kalshi_api_key")  # optional; public markets don't need it
    interval = int(config.get("poll_interval_seconds", 300))
    markets = config.get("markets", [])

    if not markets:
        log.error("No markets configured. Edit config.json and add at least one market.")
        sys.exit(1)

    log.info(
        "Starting Kalshi monitor | %d market(s) | poll every %ds | ntfy topic: %s",
        len(markets), interval, ntfy_topic,
    )

    while True:
        state = load_state()
        for m in markets:
            check_market(m, state, ntfy_topic, api_key)
        save_state(state)

        if once:
            break

        log.info("Sleeping %ds until next check…", interval)
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Kalshi price alert monitor")
    parser.add_argument("--config", default=CONFIG_FILE, help="Path to config JSON")
    parser.add_argument(
        "--once", action="store_true",
        help="Run one check then exit (useful for cron jobs)",
    )
    parser.add_argument(
        "--reset-state", action="store_true",
        help="Delete saved baseline prices and start fresh",
    )
    args = parser.parse_args()

    if args.reset_state and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        log.info("State reset.")

    if not os.path.exists(args.config):
        log.error("Config file not found: %s", args.config)
        log.error("Copy config.example.json to config.json and edit it.")
        sys.exit(1)

    config = load_config(args.config)
    run(config, once=args.once)


if __name__ == "__main__":
    main()
