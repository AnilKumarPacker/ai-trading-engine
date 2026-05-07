from flask import Flask, render_template, request
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta
import datetime
import os
import threading
import time

# -------------------------
# INIT
# -------------------------
app = Flask(__name__)

tv = TvDatafeed(
    username="hanumanthmaster1950",
    password="Tradingview123@"
)

last_cache = {}
last_updated = {}

SYMBOL_CONFIG = {
    "NIFTY": {"exchange": "NSE"},
    "BANKNIFTY": {"exchange": "NSE"},
    "SENSEX": {"exchange": "BSE"},
}

# -------------------------
# UTILS
# -------------------------
def get_ist_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)


def build_dashboard_signals(trend, alignment, dx, rsi):
    if dx > 30:
        strength = "STRONG"
        strength_color = "green"
    elif dx > 20:
        strength = "MODERATE"
        strength_color = "orange"
    else:
        strength = "WEAK"
        strength_color = "red"

    if rsi > 60:
        momentum = "BULLISH"
        momentum_color = "green"
    elif rsi < 40:
        momentum = "BEARISH"
        momentum_color = "red"
    else:
        momentum = "SIDEWAYS"
        momentum_color = "orange"

    if trend in ("BULLISH", "BEARISH") and alignment == "ALIGNED" and dx > 20:
        trade_status = "TRADE ALLOWED"
        trade_color = "green"
        decision_reason = "Daily and hourly trend are aligned, with enough directional strength."
    elif alignment == "CONFLICT":
        trade_status = "WAIT"
        trade_color = "orange"
        decision_reason = "Daily and hourly trend are not aligned. Avoid directional spreads."
    elif dx <= 20:
        trade_status = "LOW CONVICTION"
        trade_color = "orange"
        decision_reason = "Directional strength is weak. Prefer defined-risk range setups or wait."
    else:
        trade_status = "RANGE SETUP"
        trade_color = "orange"
        decision_reason = "Trend filter is neutral. Use range strategy only with clear risk limits."

    return {
        "strength": strength,
        "strength_color": strength_color,
        "momentum": momentum,
        "momentum_color": momentum_color,
        "trade_status": trade_status,
        "trade_color": trade_color,
        "decision_reason": decision_reason,
    }

# -------------------------
# SUPER TREND
# -------------------------
def add_supertrend(df, period=10, multiplier=3):

    df['ATR'] = ta.volatility.AverageTrueRange(
        df['high'], df['low'], df['close'], window=period
    ).average_true_range()

    hl2 = (df['high'] + df['low']) / 2

    df['Basic_Upper'] = hl2 + multiplier * df['ATR']
    df['Basic_Lower'] = hl2 - multiplier * df['ATR']

    df['Final_Upper'] = 0.0
    df['Final_Lower'] = 0.0
    df['Trend'] = True
    df['Supertrend'] = 0.0

    for i in range(len(df)):
        if i == 0:
            df.at[df.index[i], 'Final_Upper'] = df.iloc[i]['Basic_Upper']
            df.at[df.index[i], 'Final_Lower'] = df.iloc[i]['Basic_Lower']
            continue

        prev_close = df.iloc[i-1]['close']
        prev_upper = df.iloc[i-1]['Final_Upper']
        prev_lower = df.iloc[i-1]['Final_Lower']

        basic_upper = df.iloc[i]['Basic_Upper']
        basic_lower = df.iloc[i]['Basic_Lower']

        final_upper = basic_upper if (basic_upper < prev_upper or prev_close > prev_upper) else prev_upper
        final_lower = basic_lower if (basic_lower > prev_lower or prev_close < prev_lower) else prev_lower

        df.at[df.index[i], 'Final_Upper'] = final_upper
        df.at[df.index[i], 'Final_Lower'] = final_lower

        prev_trend = df.iloc[i-1]['Trend']

        if df.iloc[i]['close'] > final_upper:
            trend = True
        elif df.iloc[i]['close'] < final_lower:
            trend = False
        else:
            trend = prev_trend

        df.at[df.index[i], 'Trend'] = trend
        df.at[df.index[i], 'Supertrend'] = final_lower if trend else final_upper

    return df

# -------------------------
# CORE ENGINE
# -------------------------
def get_market_direction(symbol="NIFTY", exchange="NSE"):
    symbol = symbol.upper()
    exchange = SYMBOL_CONFIG.get(symbol, {}).get("exchange", exchange)

    now = get_ist_now()

    if symbol in last_cache and (now - last_updated[symbol]).seconds < 300:
        return last_cache[symbol]

    try:
        # -------------------------
        # FETCH DATA
        # -------------------------
        df_h = tv.get_hist(symbol=symbol, exchange=exchange,
                           interval=Interval.in_1_hour, n_bars=300)

        df_d = tv.get_hist(symbol=symbol, exchange=exchange,
                           interval=Interval.in_daily, n_bars=200)

        df_h = pd.DataFrame(df_h)
        df_d = pd.DataFrame(df_d)

        if df_h.empty or df_d.empty:
            raise ValueError("No data")

        # -------------------------
        # HOURLY INDICATORS
        # -------------------------
        df_h["EMA9"] = ta.trend.ema_indicator(df_h["close"], window=9)
        df_h["EMA21"] = ta.trend.ema_indicator(df_h["close"], window=21)

        dmi = ta.trend.ADXIndicator(df_h["high"], df_h["low"], df_h["close"], window=14)
        df_h["+DI"] = dmi.adx_pos()
        df_h["-DI"] = dmi.adx_neg()
        df_h["DX"] = (abs(df_h["+DI"] - df_h["-DI"]) / (df_h["+DI"] + df_h["-DI"])) * 100

        df_h = add_supertrend(df_h)

        # -------------------------
        # DAILY INDICATORS
        # -------------------------
        df_d["EMA9"] = ta.trend.ema_indicator(df_d["close"], window=9)
        df_d["EMA21"] = ta.trend.ema_indicator(df_d["close"], window=21)
        df_d = add_supertrend(df_d)

        # -------------------------
        # LAST VALUES
        # -------------------------
        last_h = df_h.iloc[-1]
        last_d = df_d.iloc[-1]

        price_h = round(last_h["close"], 2)
        dx = round(last_h["DX"], 2)
        di_plus = round(last_h["+DI"], 2)
        di_minus = round(last_h["-DI"], 2)

        # -------------------------
        # TREND LOGIC
        # -------------------------
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

        if bullish:
            trend = "BULLISH"
            color = "green"
            strategy = "Bull Put Spread"

        elif bearish:
            trend = "BEARISH"
            color = "red"
            strategy = "Bear Call Spread"

        else:
            trend = "RANGE"
            color = "orange"
            strategy = "Iron Condor"

        # -------------------------
        # EXTRA INFO
        # -------------------------
        daily_trend = "BULLISH" if last_d["Trend"] else "BEARISH"
        hourly_trend = "BULLISH" if last_h["Trend"] else "BEARISH"

        alignment = "ALIGNED" if daily_trend == hourly_trend else "CONFLICT"

        rsi = round(ta.momentum.rsi(df_h["close"], window=14).iloc[-1], 2)

        result = (
            price_h,
            round(last_h["EMA9"], 2),
            round(last_h["EMA21"], 2),
            rsi,
            di_plus,
            di_minus,
            dx,
            last_h["Trend"],
            trend,
            color,
            strategy,
            daily_trend,
            hourly_trend,
            alignment
        )

        last_cache[symbol] = result
        last_updated[symbol] = now

        return result

    except Exception as e:
        print("Error:", e)
        return (0,0,0,0,0,0,0,False,"RANGE","orange","Error","-","-","-")

# -------------------------
# ROUTE
# -------------------------
@app.route("/")
def dashboard():

    symbol = request.args.get("symbol", "NIFTY").upper()
    if symbol not in SYMBOL_CONFIG:
        symbol = "NIFTY"

    (
        price, ema9, ema21, rsi,
        di_plus, di_minus, dx,
        supertrend_bull,
        trend, color, strategy,
        daily_trend, hourly_trend, alignment
    ) = get_market_direction(symbol)

    signals = build_dashboard_signals(trend, alignment, dx, rsi)
    updated_at = last_updated.get(symbol, get_ist_now()).strftime("%d %b %Y, %I:%M %p IST")

    return render_template(
        "dashboard.html",
        symbol=symbol,
        symbols=SYMBOL_CONFIG.keys(),
        price=price,
        ema9=ema9,
        ema21=ema21,
        rsi=rsi,
        di_plus=di_plus,
        di_minus=di_minus,
        dx=dx,
        trend=trend,
        color=color,
        suggested_strategy=strategy,
        daily_trend=daily_trend,
        hourly_trend=hourly_trend,
        alignment=alignment,
        updated_at=updated_at,
        **signals
    )

# -------------------------
# BACKGROUND THREAD
# -------------------------
def hourly_updater():
    while True:
        try:
            now = get_ist_now()

            if now.minute == 2:
                for sym in SYMBOL_CONFIG:
                    get_market_direction(sym)
                time.sleep(70)

        except Exception as e:
            print("Updater error:", e)

        time.sleep(20)

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    thread = threading.Thread(target=hourly_updater)
    thread.daemon = True
    thread.start()

    app.run(host="0.0.0.0", port=10000, debug=True)
