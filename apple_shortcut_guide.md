# Kalshi Price Alert — Apple Shortcut (No Server Needed)

This Shortcut runs entirely on your iPhone.  It fetches the current Kalshi
price, compares it to the last saved value, and fires a native iOS notification
if the price has moved by your threshold.

Pair it with a **Personal Automation** set to run every 15 minutes (or
whatever interval you like) and you have a fully offline, always-on alert.

---

## 1. Find your Kalshi market ticker

1. Open [kalshi.com](https://kalshi.com) in Safari and navigate to the market
   you want to watch.
2. Look at the URL — the ticker is the last path segment, e.g.
   `https://kalshi.com/markets/kxbtcd/KXBTCD-25DEC31-T100000`
   → ticker = **`KXBTCD-25DEC31-T100000`**

---

## 2. Build the Shortcut

Open the **Shortcuts** app → tap **+** (new shortcut) → tap **Add Action**.

Add the following actions in order:

---

### Action 1 — Set your variables (edit these)
**Action:** *Text*  
**Value:** `KXBTCD-25DEC31-T100000`  
**Set Variable** → name it `ticker`

---

**Action:** *Number*  
**Value:** `3`  ← alert when price moves this many percentage points  
**Set Variable** → name it `threshold`

---

**Action:** *Text*  
**Value:** `Bitcoin above $100k`  ← friendly name shown in the notification  
**Set Variable** → name it `marketName`

---

### Action 2 — Fetch the current Kalshi price
**Action:** *Get Contents of URL*  
- URL: `https://trading-api.kalshi.com/trade-api/v2/markets/` + Variable `ticker`  
  *(tap the URL field → type the base URL → tap Variable → choose `ticker`)*  
- Method: `GET`  
- Headers: add `accept` → `application/json`

**Set Variable** → name it `apiResponse`

---

### Action 3 — Extract the YES price
**Action:** *Get Dictionary Value*  
- Dictionary: Variable `apiResponse`  
- Key: `market`  
**Set Variable** → name it `marketData`

---

**Action:** *Get Dictionary Value*  
- Dictionary: Variable `marketData`  
- Key: `yes_bid`  
**Set Variable** → name it `yesBid`

---

**Action:** *Get Dictionary Value*  
- Dictionary: Variable `marketData`  
- Key: `yes_ask`  
**Set Variable** → name it `yesAsk`

---

**Action:** *Calculate*  
- Expression: `(yesBid + yesAsk) / 2`  
  *(tap the number fields → Insert Variable → choose `yesBid` / `yesAsk`)*  
**Set Variable** → name it `currentPrice`

---

### Action 4 — Load the last saved price
**Action:** *Get File*  
- File path: `Shortcuts/kalshi_price_` + Variable `ticker` + `.txt`  
- Service: **iCloud Drive**  
- If file doesn't exist → **Continue**  
**Set Variable** → name it `savedPriceRaw`

---

**Action:** *If*  
- Condition: Variable `savedPriceRaw` **has any value**  

  *(inside the If block):*  
  **Action:** *Number from* Variable `savedPriceRaw`  
  **Set Variable** → name it `savedPrice`  

*(end If block — add an "Otherwise" block with savedPrice = currentPrice so the
first run just saves the baseline without alerting)*

---

### Action 5 — Compare and notify
**Action:** *Calculate*  
- Expression: `currentPrice - savedPrice`  
**Set Variable** → name it `delta`

---

**Action:** *If*  
- Condition: Variable `delta` **is greater than or equal to** Variable `threshold`  
**OR**  
- Condition: Variable `delta` **is less than or equal to** `-threshold`  
  *(add a second condition using **Any** — tap the condition row to switch to Any)*  

  *(inside the If block):*  

  **Action:** *Show Notification*  
  - Title: `📈 Kalshi Alert: ` + Variable `marketName`  
  - Body: `Moved ` + Variable `delta` + ` pp → now ` + Variable `currentPrice` + `%`  
  - Sound: on  

*(end If block)*

---

### Action 6 — Save the current price
**Action:** *Text*  
- Value: Variable `currentPrice`

**Action:** *Save File*  
- File path: `Shortcuts/kalshi_price_` + Variable `ticker` + `.txt`  
- Service: **iCloud Drive**  
- Overwrite: **on**

---

## 3. Set up a Personal Automation (runs automatically)

1. Shortcuts app → **Automation** tab → **+** → **Personal Automation**
2. Choose **Time of Day**
3. Set a **Start Time** (e.g. 8:00 AM) and **Repeat: Hourly** (or Every 15 Minutes)
4. Tap **Next** → **Add Action** → **Run Shortcut** → choose your shortcut
5. Toggle **Ask Before Running** → **OFF**
6. Tap **Done**

Your iPhone will now check Kalshi on schedule and buzz you the moment the price
moves by your threshold.

---

## 4. Watch multiple markets

Duplicate the Shortcut and change the `ticker`, `marketName`, and `threshold`
variables at the top.  Add one automation trigger per shortcut.

---

## Tips

| Goal | What to change |
|---|---|
| Only alert on price going **up** | Change `delta >= threshold` condition, remove the negative check |
| Only alert going **down** | Keep only the `delta <= -threshold` condition |
| Reset baseline | Delete `Shortcuts/kalshi_price_<ticker>.txt` from iCloud Drive |
| See the raw API response | Add a **Show Result** action right after the Get Contents step |
