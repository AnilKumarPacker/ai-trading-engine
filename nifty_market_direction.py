from flask import Flask, render_template
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta
import datetime
import os

app = Flask(__name__)
tv = TvDatafeed()

log_file = "daily_log.csv"
LOG_COLUMNS = ["Date", "Time", "Price", "Trend", "DX", "Suggested Strategy"]


def load_log_dataframe():
    if not os.path.exists(log_file):
        return pd.DataFrame(columns=LOG_COLUMNS)

    try:
        df = pd.read_csv(log_file)
    except Exception:
        return pd.DataFrame(columns=LOG_COLUMNS)

    df.columns = [str(column).strip() for column in df.columns]

    for column in LOG_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    return df[LOG_COLUMNS].copy()

# Initialize or reset daily log

def init_daily_log():
    df_check = load_log_dataframe()
    df_check.to_csv(log_file, index=False)

# Append new row to log

def update_log(price, trend, dx, suggested_strategy):
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:00")

    new_row = {
        "Date": date,
        "Time": time,
        "Price": price,
        "Trend": trend,
        "DX": dx,
        "Suggested Strategy": suggested_strategy
    }

    df = load_log_dataframe()

    existing = (df["Date"].astype(str) == date) & (df["Time"].astype(str) == time)

    if existing.any():
        for column, value in new_row.items():
            df.loc[existing, column] = value
    else:
        df.loc[len(df)] = new_row

    df.to_csv(log_file, index=False)


# Supertrend calculation

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
            df.iloc[i, df.columns.get_loc('Final_Upper')] = df.iloc[i]['Basic_Upper']
            df.iloc[i, df.columns.get_loc('Final_Lower')] = df.iloc[i]['Basic_Lower']
            df.iloc[i, df.columns.get_loc('Supertrend')] = df.iloc[i]['Basic_Lower']
            continue

        prev_close = df.iloc[i-1]['close']
        prev_upper = df.iloc[i-1]['Final_Upper']
        prev_lower = df.iloc[i-1]['Final_Lower']

        basic_upper = df.iloc[i]['Basic_Upper']
        basic_lower = df.iloc[i]['Basic_Lower']

        # Final upper band
        if basic_upper < prev_upper or prev_close > prev_upper:
            final_upper = basic_upper
        else:
            final_upper = prev_upper

        # Final lower band
        if basic_lower > prev_lower or prev_close < prev_lower:
            final_lower = basic_lower
        else:
            final_lower = prev_lower

        df.iloc[i, df.columns.get_loc('Final_Upper')] = final_upper
        df.iloc[i, df.columns.get_loc('Final_Lower')] = final_lower

        # Trend logic
        prev_trend = df.iloc[i-1]['Trend']

        if df.iloc[i]['close'] > final_upper:
            trend = True
        elif df.iloc[i]['close'] < final_lower:
            trend = False
        else:
            trend = prev_trend

        df.iloc[i, df.columns.get_loc('Trend')] = trend

        # Actual SuperTrend value
        if trend:
            df.iloc[i, df.columns.get_loc('Supertrend')] = final_lower
        else:
            df.iloc[i, df.columns.get_loc('Supertrend')] = final_upper

    return df


# Compute market direction

def get_market_direction():

    try:
        data = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_1_hour, n_bars=200)
        df = pd.DataFrame(data)

        if df.empty:
            raise ValueError("No market data received from TradingView")

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

        last = df.iloc[-2]
    except Exception as exc:
        app.logger.warning(f"Falling back to placeholder market data: {exc}")

        return (
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            False,
            0.0,
            "RANGE",
            "orange",
            "Data unavailable: check TradingView/network connectivity"
        )

    price = round(last["close"],2)
    open_price = round(last["open"],2)
    high_price = round(last["high"],2)
    low_price = round(last["low"],2)
    close_price = round(last["close"],2)

    ema9 = round(last["EMA9"],2)
    ema21 = round(last["EMA21"],2)
    rsi = round(last["RSI"],2)

    di_plus = round(last["+DI"],2)
    di_minus = round(last["-DI"],2)
    dx = round(last["DX"],2)

    supertrend_bull = last["Trend"]
    supertrend_value = round(last["Supertrend"], 2)

    # Directional bias
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

    return (
        price,
        open_price,
        high_price,
        low_price,
        close_price,
        ema9,
        ema21,
        rsi,
        di_plus,
        di_minus,
        dx,
        supertrend_bull,
        supertrend_value,
        trend,
        color,
        suggested_strategy
    )


@app.route("/")
def dashboard():

    init_daily_log()

    (
        price,
        open_price,
        high_price,
        low_price,
        close_price,
        ema9,
        ema21,
        rsi,
        di_plus,
        di_minus,
        dx,
        supertrend_bull,
        supertrend_value,
        trend,
        color,
        suggested_strategy
    ) = get_market_direction()

    update_log(price, trend, dx, suggested_strategy)

    df_log = pd.read_csv(log_file)
    df_log = df_log[::-1]
    log_records = df_log.to_dict(orient="records")

    return render_template(
    "dashboard.html",
    price=price,
    open=open_price,
    high=high_price,
    low=low_price,
    close=close_price,
    ema9=ema9,
    ema21=ema21,
    rsi=rsi,
    di_plus=di_plus,
    di_minus=di_minus,
    dx=dx,
    supertrend_bull=supertrend_bull,
    supertrend_value=supertrend_value,
    trend=trend,
    color=color,
    suggested_strategy=suggested_strategy,
    log_records=log_records
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
