# Kalshi Sports Price Alerts for iOS

Automatically watches **all** Kalshi sports markets and sends a native iOS push
notification whenever a market moves by your configured threshold.

Runs as a background service on your Mac mini.  Uses
[ntfy](https://ntfy.sh) for free push notifications — no Apple Developer
account required.

---

## How it works

1. Every 5 minutes (configurable) the script fetches all open Kalshi sports markets
2. If any market's YES price has moved ≥ your threshold since the last alert, a push notification fires to your iPhone
3. The baseline resets after each alert so you keep getting notified on continued moves

---

## Mac mini setup (one time)

### 1. Install Python dependencies

Open Terminal on your Mac mini:

```bash
cd /path/to/this/folder
pip3 install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.json config.json
open config.json   # edit in TextEdit or any editor
```

The only required fields:

| Field | What to set |
|---|---|
| `ntfy_topic` | A unique string like `kalshi-sports-abc123` — this is your private channel |
| `default_threshold_percent` | Minimum move (in percentage points) to trigger an alert. `5` is a good starting point |
| `default_direction` | `"both"` to alert on any move, `"up"` or `"down"` to filter |

Per-market overrides are optional — use them if you want a different threshold
on a specific market.  Run `python3 kalshi_monitor.py --list-markets` to see all
available tickers and their current prices.

### 3. Install the ntfy app on your iPhone

1. Download **ntfy** from the [App Store](https://apps.apple.com/app/ntfy/id1625396347) (free)
2. Tap **+** → enter the exact topic name you put in `config.json`
3. Enable notifications when prompted

### 4. Test it

```bash
python3 kalshi_monitor.py --once
```

You should see it fetch markets and log them.  To force a test notification,
temporarily set `default_threshold_percent` to `0.1`, run `--once`, then set it back.

### 5. Install as a background service (auto-starts on login)

```bash
python3 kalshi_monitor.py --install-mac-service
launchctl load ~/Library/LaunchAgents/com.kalshi.monitor.plist
```

The service will:
- Start automatically when you log in to your Mac
- Restart itself if it ever crashes
- Log output to `~/Library/Logs/kalshi_monitor.log`

**To view live logs:**
```bash
tail -f ~/Library/Logs/kalshi_monitor.log
```

**To stop the service:**
```bash
launchctl unload ~/Library/LaunchAgents/com.kalshi.monitor.plist
```

---

## Notifications

```
📈 Kalshi Sports: Chiefs to win Super Bowl
Moved up 6.2 pp
41.0% → 47.2%
```

```
📉 Kalshi Sports: Lakers to win NBA Championship
Moved down 5.1 pp
28.3% → 23.2%
```

---

## Useful commands

```bash
# See all current sports markets and their prices
python3 kalshi_monitor.py --list-markets

# Run one check manually (good for testing)
python3 kalshi_monitor.py --once

# Reset all saved baselines (start fresh)
python3 kalshi_monitor.py --reset-state --once
```

---

## Files

```
kalshi_monitor.py        Main monitoring script
config.example.json      Template config — copy to config.json
requirements.txt         pip dependencies (just requests)
apple_shortcut_guide.md  Alternative: no-server Shortcut setup for iPhone
```
