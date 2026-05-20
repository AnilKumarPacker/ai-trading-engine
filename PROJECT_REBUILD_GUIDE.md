# AI Trading Engine Rebuild Guide

This document is intended to give Codex enough context to recreate the project from scratch. The active app is a Flask trading dashboard for Indian indices with trend detection, option-chain retrieval through OpenAlgo, and option-spread strike selection based on 20-delta short legs plus 500-point protection legs.

## Project Goal

Build a Flask web dashboard that supports `NIFTY`, `BANKNIFTY`, and `SENSEX`.

The dashboard must:

- Fetch hourly and daily OHLC data from TradingView via `tvdatafeed`.
- Calculate EMA, RSI, DMI/DX, and Supertrend.
- Classify market trend as `BULLISH`, `BEARISH`, or `RANGE`.
- Fetch option expiry and option chain from a local OpenAlgo server.
- Parse option symbols, calculate option delta, and build a normalized option chain.
- Select strategy legs:
  - `BULLISH`: Bull Put Spread.
  - `BEARISH`: Bear Call Spread.
  - `RANGE`: Iron Condor.
- Display summary metrics, trend state, decision state, selected option legs, and option-chain table in the UI.

## Runtime

Primary app:

```bash
python app.py
```

Flask should run on:

```text
0.0.0.0:10000
```

Open in browser:

```text
http://127.0.0.1:10000/?symbol=NIFTY
http://127.0.0.1:10000/?symbol=BANKNIFTY
http://127.0.0.1:10000/?symbol=SENSEX
```

There is also an older app in `nifty_market_direction.py`, and deployment files currently point to it. For recreating the current option-chain dashboard, use `app.py` as the active entrypoint.

## Dependencies

`requirements.txt`:

```text
flask
pandas
numpy
ta
git+https://github.com/rongardF/tvdatafeed.git
requests
websocket-client
py_vollib
```

The current `option_engine.py` calculates delta manually and does not require `py_vollib`, but keep it if compatibility with earlier code matters.

## Environment Variables

OpenAlgo:

```text
OPENALGO_BASE_URL=http://127.0.0.1:5000
OPENALGO_API_KEY=<local OpenAlgo API key>
```

Optional spot fallbacks if the OpenAlgo option-chain response does not include `atm_strike`, `atm`, `spot`, `spot_price`, or `underlying_ltp`:

```text
UNDERLYING_PRICE=<spot>
NIFTY_SPOT=<spot>
BANKNIFTY_SPOT=<spot>
SENSEX_SPOT=<spot>
```

TradingView credentials are currently hard-coded in `data_fetch.py`. A cleaner rebuild should move them to environment variables.

## File Layout

Required active files:

```text
app.py
data_fetch.py
indicators.py
trend_engine.py
option_engine.py
templates/dashboard.html
requirements.txt
```

Supporting or legacy files:

```text
nifty_market_direction.py
openalgo_service.py
test.py
templates/backtest.html
templates/dashboard_bkp.html
templates/dashboard1.txt
render.yaml
start.sh
```

## app.py

Responsibilities:

- Create Flask app.
- Define supported symbols:

```python
SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
TREND_EXCHANGES = {"SENSEX": "BSE"}
```

- Default exchange for trend data is `NSE`; `SENSEX` uses `BSE`.
- Route `/` reads query param `symbol`, validates it, and defaults to `NIFTY`.
- Calls:

```python
get_market_direction(symbol, exchange=trend_exchange)
SimpleOptionChain(underlying=symbol).get_option_chain()
select_strikes(option_chain, trend)
```

`get_market_direction` returns this tuple:

```python
(
    price, ema9, ema21, rsi,
    di_plus, di_minus, dx,
    supertrend_bull,
    trend, color, strategy,
    daily_trend, hourly_trend, alignment
)
```

Dashboard signal helper:

- Strength from `dx`:
  - `dx > 30`: `STRONG`, green.
  - `dx > 20`: `MODERATE`, orange.
  - Else: `WEAK`, red.
- Momentum from `rsi`:
  - `rsi > 60`: `BULLISH`, green.
  - `rsi < 40`: `BEARISH`, red.
  - Else: `SIDEWAYS`, orange.
- Trade status:
  - Directional trend + aligned + `dx > 20`: `TRADE ALLOWED`, green.
  - Alignment conflict: `WAIT`, orange.
  - `dx <= 20`: `LOW CONVICTION`, orange.
  - Else: `RANGE SETUP`, orange.

Render `templates/dashboard.html` with:

```python
symbol
symbols
updated_at
price
ema9
ema21
rsi
di_plus
di_minus
dx
trend
color
suggested_strategy
daily_trend
hourly_trend
alignment
option_chain
option_strategy
strength
strength_color
momentum
momentum_color
trade_status
trade_color
decision_reason
```

Avoid printing the full option chain in request flow because it is large and slows the app.

## data_fetch.py

Responsibilities:

- Instantiate `TvDatafeed`.
- Fetch hourly and daily data:

```python
df_h = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_1_hour, n_bars=300)
df_d = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_daily, n_bars=200)
```

- Convert both to pandas DataFrames.
- Raise `ValueError("No data")` if either DataFrame is empty.
- Return `(df_h, df_d)`.

## indicators.py

Responsibilities:

`add_indicators(df)`:

- EMA9: `ta.trend.ema_indicator(df["close"], window=9)`
- EMA21: `ta.trend.ema_indicator(df["close"], window=21)`
- DMI:

```python
dmi = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
df["+DI"] = dmi.adx_pos()
df["-DI"] = dmi.adx_neg()
df["DX"] = (abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])) * 100
```

`add_supertrend(df, period=10, multiplier=3)`:

- Use ATR from `ta.volatility.AverageTrueRange`.
- Compute basic upper/lower bands from `hl2 +/- multiplier * ATR`.
- Maintain `Final_Upper`, `Final_Lower`, boolean `Trend`, and numeric `Supertrend`.
- If close crosses above final upper, trend is bullish.
- If close crosses below final lower, trend is bearish.
- Otherwise keep previous trend.
- Supertrend value is final lower in bullish trend, final upper in bearish trend.

## trend_engine.py

Responsibilities:

- Keep 5-minute in-memory cache:

```python
last_cache = {}
last_updated = {}
```

- `get_market_direction(symbol="NIFTY", exchange="NSE")`:
  - Fetch hourly/daily data.
  - Apply `add_indicators` and `add_supertrend` to hourly.
  - Add daily EMA9/EMA21 and daily Supertrend.
  - Use latest hourly and daily rows.
  - Compute:
    - `price`
    - `dx`
    - `di_plus`
    - `di_minus`
    - `rsi`

Trend logic:

```python
bullish = (
    last_d["close"] > last_d["Supertrend"] and
    last_d["close"] > last_d["EMA9"] and
    last_d["close"] > last_d["EMA21"] and
    last_h["close"] > last_h["Supertrend"]
)

bearish = (
    last_d["close"] < last_d["Supertrend"] and
    last_d["close"] < last_d["EMA9"] and
    last_d["close"] < last_d["EMA21"] and
    last_h["close"] < last_h["Supertrend"]
)
```

Output:

- If bullish:
  - `trend = "BULLISH"`
  - `color = "green"`
  - `strategy = "Bull Put Spread"`
- If bearish:
  - `trend = "BEARISH"`
  - `color = "red"`
  - `strategy = "Bear Call Spread"`
- Else:
  - `trend = "RANGE"`
  - `color = "orange"`
  - `strategy = "Iron Condor"`

Daily/hourly trend labels:

```python
daily_trend = "BULLISH" if last_d["Trend"] else "BEARISH"
hourly_trend = "BULLISH" if last_h["Trend"] else "BEARISH"
alignment = "ALIGNED" if daily_trend == hourly_trend else "CONFLICT"
```

On exception, return a tuple of zero/default values:

```python
(0,0,0,0,0,0,0,False,"RANGE","orange","Error","-","-","-")
```

## option_engine.py

Responsibilities:

- Call OpenAlgo REST APIs directly.
- Parse expiries and option symbols.
- Build normalized option chain.
- Calculate delta.
- Select option legs.

Constants:

```python
HOST = os.getenv("OPENALGO_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
API_KEY = os.getenv("OPENALGO_API_KEY", "<fallback key>")
```

Supported date formats:

```python
"%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
"%d-%b-%Y", "%d-%B-%Y", "%d-%b-%y", "%d-%B-%y",
"%d%b%y", "%d%b%Y"
```

Index config:

```python
INDEX_CONFIG = {
    "NIFTY": {
        "expiry_exchange": "NFO",
        "optionchain_exchange": "NSE_INDEX",
        "spot_env": "NIFTY_SPOT",
    },
    "BANKNIFTY": {
        "expiry_exchange": "NFO",
        "optionchain_exchange": "NSE_INDEX",
        "spot_env": "BANKNIFTY_SPOT",
    },
    "SENSEX": {
        "expiry_exchange": "BFO",
        "optionchain_exchange": "BSE_INDEX",
        "spot_env": "SENSEX_SPOT",
    },
}
```

OpenAlgo expiry request:

```http
POST {OPENALGO_BASE_URL}/api/v1/expiry
```

Payload:

```json
{
  "apikey": "...",
  "symbol": "NIFTY",
  "exchange": "NFO",
  "instrumenttype": "options"
}
```

For `SENSEX`, use exchange `BFO`.

Expiry response may be:

```json
{"data": ["28-MAY-2026", "04-JUN-2026"]}
```

Pick nearest future expiry and format as:

```text
DDMMMYY
```

Example:

```text
28MAY26
```

OpenAlgo option-chain request:

```http
POST {OPENALGO_BASE_URL}/api/v1/optionchain
```

Payload:

```json
{
  "apikey": "...",
  "underlying": "NIFTY",
  "exchange": "NSE_INDEX",
  "expiry_date": "28MAY26",
  "strike_count": 30
}
```

For:

- `NIFTY`: `NSE_INDEX`
- `BANKNIFTY`: `NSE_INDEX`
- `SENSEX`: `BSE_INDEX`

`symbols_from_response(response_json)` must recursively collect every dict value where key `symbol` exists.

`option_data_from_response(response_json)` must recursively map each symbol to the dict that contained it.

Spot/ATM:

- First try recursive keys:
  - `atm_strike`
  - `atm`
  - `spot`
  - `spot_price`
  - `underlying_ltp`
- Then try env fallback:
  - `UNDERLYING_PRICE`
  - index-specific env from `INDEX_CONFIG`.

Option symbol parser:

```text
{UNDERLYING}{EXPIRY}{STRIKE}{CE|PE}
```

Examples:

```text
NIFTY28MAY2625000CE
BANKNIFTY28MAY2651000PE
SENSEX28MAY2680000CE
```

Regex shape:

```python
rf"^{underlying}{expiry_date}(\d+(?:\.\d+)?)(CE|PE)$"
```

Delta calculation:

- Use Black-Scholes-style `d1`.
- `days_to_expiry = max((expiry.date() - today).days, 1)`
- `years_to_expiry = days_to_expiry / 365.0`
- Default volatility `0.15`, or use option response fields `iv` / `implied_volatility`.
- Risk-free rate `0.07`.
- CE delta: `normal_cdf(d1)`.
- PE delta: `normal_cdf(d1) - 1`.
- Round to 4 decimals.

Normalized option-chain return shape:

```python
{
    "underlying": "NIFTY",
    "expiry": "28MAY26",
    "spot_price": 25000.0,
    "atm_strike": 25000.0,
    "timestamp": "...Asia/Kolkata ISO timestamp...",
    "raw": response_json,
    "chain": [
        {
            "strike": 25000.0,
            "ce": {
                "symbol": "NIFTY28MAY2625000CE",
                "strike": 25000.0,
                "type": "CE",
                "ltp": 0,
                "volume": 0,
                "delta": 0.532,
                "raw": {}
            },
            "pe": {
                "symbol": "NIFTY28MAY2625000PE",
                "strike": 25000.0,
                "type": "PE",
                "ltp": 0,
                "volume": 0,
                "delta": -0.468,
                "raw": {}
            }
        }
    ]
}
```

Market values:

- `ltp` should read first available key among `ltp`, `lp`, `last_price`.
- `volume` should read first available key among `volume`, `v`, `vol`.
- Default to `0`.

Strike window:

- `SimpleOptionChain(..., strike_count=30)` by default.
- Keep 30 strikes each side around ATM after parsing.
- This is important because the selected buy/protection strike must be 500+ points away from the selected sell strike.

## Strike Selection Rules

Use `select_strikes(chain_json, trend)`.

Normalize `chain_json["chain"]` to flat options:

```python
[
    {"strike": 25000.0, "type": "CE", "symbol": "...", "ltp": 0, "volume": 0, "delta": 0.532},
    {"strike": 25000.0, "type": "PE", "symbol": "...", "ltp": 0, "volume": 0, "delta": -0.468},
]
```

Delta normalization:

- If API returns `20`, treat it as `0.20`.
- PE deltas are negative. Use absolute delta for matching.

Short-leg selection:

- Prefer option whose absolute delta is between `0.20` and `0.21`.
- If no exact fair candidate exists, choose option with absolute delta nearest `0.20`.

Protection-leg selection:

- Must be at least 500 strike points farther from the short leg.
- For PE protection: choose the highest strike that is `<= sell_strike - 500`.
- For CE protection: choose the lowest strike that is `>= sell_strike + 500`.

Trend behavior:

`BULLISH`:

- Use OTM PE options where `strike < atm`.
- `sell = 20-delta PE`.
- `buy = PE at least 500 points lower`.
- Return:

```python
{
    "strategy": "Bull Put Spread",
    "sell": sell,
    "buy": buy
}
```

`BEARISH`:

- Use OTM CE options where `strike > atm`.
- `sell = 20-delta CE`.
- `buy = CE at least 500 points higher`.
- Return:

```python
{
    "strategy": "Bear Call Spread",
    "sell": sell,
    "buy": buy
}
```

`RANGE`:

- Use OTM CE and OTM PE.
- `sell_ce = 20-delta CE`.
- `buy_ce = CE at least 500 points higher`.
- `sell_pe = 20-delta PE`.
- `buy_pe = PE at least 500 points lower`.
- Return:

```python
{
    "strategy": "Iron Condor",
    "sell_ce": sell_ce,
    "buy_ce": buy_ce,
    "sell_pe": sell_pe,
    "buy_pe": buy_pe
}
```

If a protection leg is not visible in the UI, the likely reason is that the option chain does not include strikes far enough away. Increase `strike_count`.

## templates/dashboard.html

Use a dark dashboard UI.

Required sections:

1. Top bar:
   - Title: `{symbol} Trading Dashboard`
   - `updated_at`
   - Symbol tabs for `NIFTY`, `BANKNIFTY`, `SENSEX`
   - Backtest tab may link to `/backtest?symbol={{symbol}}&run=0`

2. Market summary cards:
   - Price
   - Final Trend
   - Strength
   - Strategy

3. Multi-timeframe trend card:
   - Daily Trend
   - Hourly Trend
   - Momentum
   - Alignment badge

4. Decision Engine card:
   - Market Type
   - Strength
   - Momentum
   - Suggested Strategy
   - Trade status badge
   - Decision reason

5. Option Chain card:
   - Strategy badge from `option_strategy.strategy`.
   - Metadata badges:
     - Expiry
     - Spot
     - ATM
   - Strategy leg cards:
     - `sell` and `buy` for bull/bear spreads.
     - `sell_ce`, `buy_ce`, `sell_pe`, `buy_pe` for Iron Condor.
   - Scrollable table with columns:
     - Call Symbol
     - Call LTP
     - Call Vol
     - Call Delta
     - Strike
     - Put Delta
     - Put Vol
     - Put LTP
     - Put Symbol
   - Highlight row where `row.strike == option_chain.atm_strike`.

CSS:

- Dark background.
- Cards with 8px border radius.
- Responsive grids.
- Option table should use `overflow-x: auto` and `min-width` around `860px`.
- Use color classes:
  - `.green`
  - `.red`
  - `.orange`
  - `.blue`

## test.py

`test.py` is a standalone reference script for OpenAlgo REST calls.

Important pieces copied into `option_engine.py`:

- `DATE_FORMATS`
- `parse_expiry_date`
- `nearest_date_from_response`
- `symbols_from_response`
- `parse_float`
- `atm_strike_from_response`
- `parse_option_symbol`
- `normal_cdf`
- `calculate_delta`

Do not make the Flask app import `test.py`; keep it as a scratch/reference script.

## openalgo_service.py

Legacy helper for `client.optiongreeks`. The current active option engine calculates delta locally and does not use this file.

## Deployment Notes

Current `render.yaml`:

```yaml
services:
  - type: web
    name: trade-dashboard
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: python nifty_market_direction.py
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.9
```

For the current active `app.py`, update deployment start command to:

```yaml
startCommand: python app.py
```

Current `start.sh` runs:

```bash
python nifty_market_direction.py
```

For current app, change to:

```bash
python app.py
```

## Rebuild Checklist

1. Create Python Flask project.
2. Add dependencies from `requirements.txt`.
3. Implement `data_fetch.py`.
4. Implement `indicators.py`.
5. Implement `trend_engine.py`.
6. Implement `option_engine.py` with OpenAlgo REST expiry/option-chain flow.
7. Implement `app.py`.
8. Create `templates/dashboard.html`.
9. Run:

```bash
python3 -m py_compile app.py option_engine.py trend_engine.py indicators.py data_fetch.py
python app.py
```

10. Verify URLs:

```text
/?symbol=NIFTY
/?symbol=BANKNIFTY
/?symbol=SENSEX
```

11. If selected buy leg is missing, increase `strike_count` in `SimpleOptionChain`.

## Important Implementation Preferences

- Do not print full option-chain payloads during web requests.
- Keep `select_strikes` independent from Flask.
- Keep `option_engine.py` tolerant of nested and changing OpenAlgo response shapes.
- Keep returned option-chain shape stable because the dashboard depends on it.
- Prefer environment variables for API keys and credentials in a clean rebuild.
