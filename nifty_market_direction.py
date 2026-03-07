from flask import Flask, render_template
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta
import datetime
import os
import csv

app = Flask(__name__)
tv = TvDatafeed()

log_file = "daily_log.csv"

# Initialize or reset daily log
def init_daily_log():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(log_file):
        # Check if last entry is from today
        df_check = pd.read_csv(log_file)
        if df_check.empty or df_check.iloc[-1]["Date"] != today:
            # New day → overwrite headers
            with open(log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Time", "Price", "Trend", "DX", "Suggested Strategy"])
    else:
        # File doesn't exist → create headers
        with open(log_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Time", "Price", "Trend", "DX", "Suggested Strategy"])

# Append new row to log
def update_log(price, trend, dx, suggested_strategy):
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M")
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([date, time, price, trend, dx, suggested_strategy])

# Supertrend function
def add_supertrend(df, period=10, multiplier=3):
    df['ATR'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=period).average_true_range()
    df['Basic_Upper'] = (df['high'] + df['low']) / 2 + multiplier * df['ATR']
    df['Basic_Lower'] = (df['high'] + df['low']) / 2 - multiplier * df['ATR']
    df['Final_Upper'] = 0.0
    df['Final_Lower'] = 0.0
    df['Supertrend'] = True

    for i in range(len(df)):
        if i == 0:
            df.at[i, 'Final_Upper'] = df.at[i, 'Basic_Upper']
            df.at[i, 'Final_Lower'] = df.at[i, 'Basic_Lower']
        else:
            df.at[i, 'Final_Upper'] = min(df.at[i, 'Basic_Upper'], df.at[i-1, 'Final_Upper']) if df.at[i-1, 'close'] <= df.at[i-1, 'Final_Upper'] else df.at[i, 'Basic_Upper']
            df.at[i, 'Final_Lower'] = max(df.at[i, 'Basic_Lower'], df.at[i-1, 'Final_Lower']) if df.at[i-1, 'close'] >= df.at[i-1, 'Final_Lower'] else df.at[i, 'Basic_Lower']

        if df.at[i, 'close'] > df.at[i, 'Final_Lower']:
            df.at[i, 'Supertrend'] = True
        elif df.at[i, 'close'] < df.at[i, 'Final_Upper']:
            df.at[i, 'Supertrend'] = False

    return df

# Compute market direction
def get_market_direction():
    data = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_1_hour, n_bars=200)
    df = pd.DataFrame(data)

    # Indicators
    df["EMA9"] = ta.trend.ema_indicator(df["close"], window=9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], window=21)
    df["RSI"] = ta.momentum.rsi(df["close"], window=14)

    # DMI
    dmi = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["+DI"] = dmi.adx_pos()
    df["-DI"] = dmi.adx_neg()
    df["DX"] = (abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])) * 100

    # Supertrend
    df = add_supertrend(df)
    last = df.iloc[-1]

    price = round(last["close"],2)
    ema9 = round(last["EMA9"],2)
    ema21 = round(last["EMA21"],2)
    rsi = round(last["RSI"],2)
    di_plus = round(last["+DI"],2)
    di_minus = round(last["-DI"],2)
    dx = round(last["DX"],2)
    supertrend_bull = last["Supertrend"]

    # Directional bias logic
    if di_plus > di_minus and dx > 20 and supertrend_bull:
        trend = "BULLISH"
        color = "green"
        suggested_strategy = "Bull Put Spread / Bull Call Spread"
    elif di_minus > di_plus and dx > 20 and not supertrend_bull:
        trend = "BEARISH"
        color = "red"
        suggested_strategy = "Bear Call Spread / Bear Put Spread"
    else:
        trend = "RANGE"
        color = "orange"
        suggested_strategy = "Iron Condor / Short Strangle"

    return price, ema9, ema21, rsi, di_plus, di_minus, dx, supertrend_bull, trend, color, suggested_strategy

@app.route("/")
def dashboard():
    init_daily_log()
    price, ema9, ema21, rsi, di_plus, di_minus, dx, supertrend_bull, trend, color, suggested_strategy = get_market_direction()
    update_log(price, trend, dx, suggested_strategy)

    df_log = pd.read_csv(log_file)
    df_log = df_log[::-1]
    log_records = df_log.to_dict(orient="records")

    return render_template(
        "dashboard.html",
        price=price,
        ema9=ema9,
        ema21=ema21,
        rsi=rsi,
        di_plus=di_plus,
        di_minus=di_minus,
        dx=dx,
        supertrend_bull=supertrend_bull,
        trend=trend,
        color=color,
        suggested_strategy=suggested_strategy,
        log_records=log_records
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)