#!/usr/bin/env python3
"""
Kalshi Sports Price Alert Monitor
Automatically watches ALL Kalshi sports markets and sends iOS push notifications
via ntfy.sh when a price moves by your configured threshold.

Setup:
  1. pip install -r requirements.txt
  2. cp config.example.json config.json  →  edit ntfy_topic and thresholds
  3. Install ntfy on iPhone, subscribe to your topic
  4. python kalshi_monitor.py

To install as a background Mac service that auto-starts on login:
  python kalshi_monitor.py --install-mac-service
  launchctl load ~/Library/LaunchAgents/com.kalshi.monitor.plist

Kalshi API docs: https://trading-api.kalshi.com/trade-api/v2/docs
ntfy docs:       https://ntfy.sh/docs/
"""

import json
import os
import sys
import time
import logging
import argparse
import subprocess
from datetime import datetime
from typing import Optional

import requests

CONFIG_FILE = "config.json"
STATE_FILE = ".alert_state.json"
PLIST_NAME = "com.kalshi.monitor"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"


# ---------------------------------------------------------------------------
# Kalshi API
# ---------------------------------------------------------------------------

def _get(path: str, params: dict = None, api_key: str = None) -> dict:
    headers = {"accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.get(f"{KALSHI_BASE}{path}", headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_all_sports_markets(api_key: Optional[str] = None) -> list[dict]:
    """
    Return every active sports market from Kalshi, handling pagination.
    Each item is a market dict with at minimum: ticker, title, yes_bid, yes_ask, last_price.
    """
    markets = []
    cursor = None

    while True:
        params = {"status": "open", "limit": 200}
        # Kalshi uses 'category' for broad groupings
        # The sports category label on Kalshi is "sports"
        params["category"] = "Sports"
        if cursor:
            params["cursor"] = cursor

        try:
            data = _get("/markets", params=params, api_key=api_key)
        except requests.HTTPError as exc:
            log.error("Error fetching markets: %s", exc)
            break

        batch = data.get("markets", [])
        markets.extend(batch)

        cursor = data.get("cursor")
        if not cursor or not batch:
            break

    log.info("Fetched %d open sports markets from Kalshi", len(markets))
    return markets


def get_yes_price(market: dict) -> Optional[float]:
    """Return the YES mid-price as a percentage (0-100)."""
    bid = market.get("yes_bid")
    ask = market.get("yes_ask")
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    last = market.get("last_price")
    return float(last) if last is not None else None


# ---------------------------------------------------------------------------
# ntfy.sh push notifications
# ---------------------------------------------------------------------------

def send_notification(topic: str, title: str, message: str, tags: list[str] | None = None):
    url = f"https://ntfy.sh/{topic}"
    headers = {
        "Title": title,
        "Priority": "high",
        "Tags": ",".join(tags or ["bell"]),
    }
    try:
        resp = requests.post(url, data=message.encode(), headers=headers, timeout=10)
        resp.raise_for_status()
        log.info("  ALERT SENT → %s", title)
    except requests.RequestException as exc:
        log.warning("Failed to send notification: %s", exc)


# ---------------------------------------------------------------------------
# State persistence
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

def check_market(
    market: dict,
    state: dict,
    ntfy_topic: str,
    default_threshold: float,
    default_direction: str,
    overrides: dict,
):
    ticker = market.get("ticker", "")
    name = market.get("title") or market.get("subtitle") or ticker

    # Per-market overrides take priority over defaults
    override = overrides.get(ticker, {})
    threshold = float(override.get("threshold_percent", default_threshold))
    direction = override.get("direction", default_direction).lower()
    if override.get("name"):
        name = override["name"]

    current = get_yes_price(market)
    if current is None:
        return

    entry = state.get(ticker, {})
    compare_to = entry.get("last_alerted_price") or entry.get("baseline_price")

    if compare_to is None:
        state[ticker] = {
            "baseline_price": current,
            "last_alerted_price": None,
            "last_checked": datetime.utcnow().isoformat(),
            "name": name,
        }
        return

    delta = current - compare_to

    should_alert = (
        abs(delta) >= threshold
        and (
            direction == "both"
            or (direction == "up" and delta > 0)
            or (direction == "down" and delta < 0)
        )
    )

    if should_alert:
        word = "up" if delta > 0 else "down"
        emoji = "📈" if delta > 0 else "📉"
        title = f"{emoji} Kalshi Sports: {name}"
        msg = (
            f"Moved {word} {abs(delta):.1f} pp\n"
            f"{compare_to:.1f}% → {current:.1f}%"
        )
        tag = "chart_with_upwards_trend" if delta > 0 else "chart_with_downwards_trend"
        send_notification(ntfy_topic, title, msg, tags=[tag])

        state[ticker] = {
            "baseline_price": entry.get("baseline_price", compare_to),
            "last_alerted_price": current,
            "last_checked": datetime.utcnow().isoformat(),
            "name": name,
        }
    else:
        if ticker not in state:
            state[ticker] = {}
        state[ticker]["last_checked"] = datetime.utcnow().isoformat()
        state[ticker]["name"] = name


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(config: dict, once: bool = False):
    ntfy_topic = config["ntfy_topic"]
    api_key = config.get("kalshi_api_key")
    interval = int(config.get("poll_interval_seconds", 300))
    default_threshold = float(config.get("default_threshold_percent", 5.0))
    default_direction = config.get("default_direction", "both")
    overrides = config.get("market_overrides", {})

    log.info(
        "Kalshi Sports Monitor | default threshold: %.1f pp | poll: %ds | ntfy: %s",
        default_threshold, interval, ntfy_topic,
    )

    while True:
        markets = fetch_all_sports_markets(api_key)
        state = load_state()

        for m in markets:
            check_market(m, state, ntfy_topic, default_threshold, default_direction, overrides)

        save_state(state)
        log.info("Checked %d markets. Next check in %ds.", len(markets), interval)

        if once:
            break
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Mac launchd service installer
# ---------------------------------------------------------------------------

PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
        <string>--config</string>
        <string>{config}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{workdir}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>{logdir}/kalshi_monitor.log</string>

    <key>StandardErrorPath</key>
    <string>{logdir}/kalshi_monitor_error.log</string>

    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
"""


def install_mac_service(config_path: str):
    import shutil

    python = shutil.which("python3") or sys.executable
    script = os.path.abspath(__file__)
    workdir = os.path.dirname(script)
    config_abs = os.path.abspath(config_path)
    logdir = os.path.expanduser("~/Library/Logs")
    agents_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(agents_dir, f"{PLIST_NAME}.plist")

    os.makedirs(agents_dir, exist_ok=True)
    os.makedirs(logdir, exist_ok=True)

    content = PLIST_TEMPLATE.format(
        label=PLIST_NAME,
        python=python,
        script=script,
        config=config_abs,
        workdir=workdir,
        logdir=logdir,
    )

    with open(plist_path, "w") as f:
        f.write(content)

    print(f"Plist written to: {plist_path}")
    print()
    print("To start the service now:")
    print(f"  launchctl load {plist_path}")
    print()
    print("To stop the service:")
    print(f"  launchctl unload {plist_path}")
    print()
    print("To view logs:")
    print(f"  tail -f {logdir}/kalshi_monitor.log")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Kalshi sports price alert monitor")
    parser.add_argument("--config", default=CONFIG_FILE)
    parser.add_argument("--once", action="store_true", help="Run one check then exit")
    parser.add_argument("--reset-state", action="store_true", help="Clear saved baselines")
    parser.add_argument(
        "--install-mac-service", action="store_true",
        help="Write a launchd plist so this runs automatically on your Mac",
    )
    parser.add_argument(
        "--list-markets", action="store_true",
        help="Print all current Kalshi sports markets and exit",
    )
    args = parser.parse_args()

    if args.list_markets:
        markets = fetch_all_sports_markets()
        for m in sorted(markets, key=lambda x: x.get("ticker", "")):
            price = get_yes_price(m)
            price_str = f"{price:.1f}%" if price is not None else "n/a"
            print(f"{m.get('ticker', '?'):45s}  {price_str:8s}  {m.get('title', '')}")
        return

    if args.install_mac_service:
        if not os.path.exists(args.config):
            print(f"Error: config file not found at {args.config}")
            print("Run: cp config.example.json config.json  and edit it first.")
            sys.exit(1)
        install_mac_service(args.config)
        return

    if args.reset_state and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        log.info("State reset.")

    if not os.path.exists(args.config):
        print(f"Config not found: {args.config}")
        print("Run: cp config.example.json config.json  and edit it.")
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    run(config, once=args.once)


if __name__ == "__main__":
    main()
