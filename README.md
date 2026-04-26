# Kalshi Price Alerts for iOS

Get a native iOS push notification whenever a Kalshi prediction market moves by
a configured number of percentage points.

Two approaches — pick the one that fits your setup:

---

## Option A: Python monitor + ntfy (recommended)

Runs on any always-on machine (Mac, Linux server, Raspberry Pi, free cloud VM).
Sends real push notifications to your iPhone via the free
[ntfy](https://ntfy.sh) app — no Apple Developer account needed.

### Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure markets and threshold
cp config.example.json config.json
# Edit config.json — set your ntfy topic and add your Kalshi tickers

# 3. Install the ntfy app on your iPhone
#    App Store: https://apps.apple.com/app/ntfy/id1625396347
#    Subscribe to the same topic you put in config.json

# 4. Run (keep it running in a screen/tmux session or as a systemd service)
python kalshi_monitor.py

# One-shot mode (great for cron)
python kalshi_monitor.py --once
```

### config.json fields

| Field | Description |
|---|---|
| `ntfy_topic` | A unique string — this is your "channel". Use something hard to guess, e.g. `kalshi-alerts-abc123` |
| `kalshi_api_key` | Optional. Leave blank for public markets |
| `poll_interval_seconds` | How often to check (default 300 = every 5 min) |
| `markets[].ticker` | Kalshi ticker from the market URL |
| `markets[].alert_threshold_percent` | Minimum move (in percentage points) to trigger an alert |
| `markets[].direction` | `"up"`, `"down"`, or `"both"` |

### Finding a Kalshi ticker

Go to a market on [kalshi.com](https://kalshi.com).  The ticker is the last
segment of the URL, e.g. `KXBTCD-25DEC31-T100000`.

### Running as a cron job

```cron
# Check every 5 minutes
*/5 * * * * /usr/bin/python3 /path/to/kalshi_monitor.py --once >> /var/log/kalshi.log 2>&1
```

---

## Option B: Apple Shortcut (no server needed)

Runs entirely on your iPhone using the Shortcuts app.  Checks Kalshi on a
schedule, compares to the last saved price, and fires a native notification.

→ See **[apple_shortcut_guide.md](apple_shortcut_guide.md)** for step-by-step
  instructions.

---

## How alerts look

```
📈 Kalshi Alert: Bitcoin above $100k
Moved +4.2 pp → now 67.3%
```

---

## Files

```
kalshi_monitor.py        Python monitoring script
config.example.json      Template config (copy → config.json)
requirements.txt         pip dependencies
apple_shortcut_guide.md  Step-by-step Shortcut setup for iPhone
```
