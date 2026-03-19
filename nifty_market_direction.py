from flask import Flask, render_template
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta
import datetime
import os
import threading
import time
import requests
from option_engine import build_strategy, format_strategy
#from kotak_option_chain import get_kotak_option_chain

app = Flask(__name__)
tv = TvDatafeed()

log_file = "daily_log.csv"

LOG_COLUMNS = [
    "Date",
    "Time",
    "Price",
    "Trend",
    "DX",
    "Suggested Strategy"
]


def get_ist_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)


def is_market_hours(dt):
    market_open = dt.replace(hour=9, minute=15, second=0)
    market_close = dt.replace(hour=15, minute=30, second=0)
    return market_open <= dt <= market_close

def get_option_chain():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"

    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
        'accept-language': 'en-US,en;q=0.9', 'accept-encoding': 'gzip, deflate, br'
    }

    r = requests.get(url, headers=headers).json()
    data = r
    print("Option chain keys:", data)
    #print("Underlying:", data["records"]["underlyingValue"])
    return data


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


def init_daily_log():

    df = load_log_dataframe()
    df.to_csv(log_file, index=False)


def write_full_hourly_log(rows):

    df = pd.DataFrame(rows)

    if df.empty:
        return

    if os.path.exists(log_file):
        old = pd.read_csv(log_file)
        df = pd.concat([old, df])

    df.drop_duplicates(subset=["Date", "Time"], keep="last", inplace=True)

    df.sort_values(["Date", "Time"], inplace=True)

    df.to_csv(log_file, index=False)


def build_hourly_log(df):

    now = get_ist_now()
    today = now.strftime("%Y-%m-%d")

    rows = []

    for i in range(len(df)):

        candle_time = df.index[i]

        candle_time = candle_time + datetime.timedelta(hours=5, minutes=30)

        if candle_time.strftime("%Y-%m-%d") != today:
            continue

        if not is_market_hours(candle_time):
            continue

        price = round(df.iloc[i]["close"], 2)

        di_plus = df.iloc[i]["+DI"]
        di_minus = df.iloc[i]["-DI"]
        dx = df.iloc[i]["DX"]

        supertrend_bull = df.iloc[i]["Trend"]

        if di_plus > di_minus and dx > 20 and supertrend_bull:
            trend = "BULLISH"
            strategy = "Bull Put Spread / Bull Call Spread"

        elif di_minus > di_plus and dx > 20 and not supertrend_bull:
            trend = "BEARISH"
            strategy = "Bear Call Spread / Bear Put Spread"

        else:
            trend = "RANGE"
            strategy = "Iron Condor / Short Strangle"

        rows.append({
            "Date": candle_time.strftime("%Y-%m-%d"),
            "Time": candle_time.strftime("%H:00"),
            "Price": price,
            "Trend": trend,
            "DX": round(dx, 2),
            "Suggested Strategy": strategy
        })

    return rows
    
def get_dummy_option_chain(price):

    base = int(round(price / 50) * 50)

    chain = []

    for i in range(-6, 7):

        strike = base + (i * 50)

        # fake delta logic just for testing
        delta_call = max(0.05, min(0.5, 0.5 - abs(i)*0.05))
        delta_put = -delta_call

        chain.append({
            "strike": strike,
            "type": "CE",
            "delta": round(delta_call, 2)
        })

        chain.append({
            "strike": strike,
            "type": "PE",
            "delta": round(delta_put, 2)
        })

    return chain


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

        if basic_upper < prev_upper or prev_close > prev_upper:
            final_upper = basic_upper
        else:
            final_upper = prev_upper

        if basic_lower > prev_lower or prev_close < prev_lower:
            final_lower = basic_lower
        else:
            final_lower = prev_lower

        df.iloc[i, df.columns.get_loc('Final_Upper')] = final_upper
        df.iloc[i, df.columns.get_loc('Final_Lower')] = final_lower

        prev_trend = df.iloc[i-1]['Trend']

        if df.iloc[i]['close'] > final_upper:
            trend = True
        elif df.iloc[i]['close'] < final_lower:
            trend = False
        else:
            trend = prev_trend

        df.iloc[i, df.columns.get_loc('Trend')] = trend

        if trend:
            df.iloc[i, df.columns.get_loc('Supertrend')] = final_lower
        else:
            df.iloc[i, df.columns.get_loc('Supertrend')] = final_upper

    return df


def get_market_direction():

    try:

        data = tv.get_hist(
            symbol='NIFTY',
            exchange='NSE',
            interval=Interval.in_1_hour,
            n_bars=300
        )

        df = pd.DataFrame(data)

        if df.empty:
            raise ValueError("No market data received")

        df["EMA9"] = ta.trend.ema_indicator(df["close"], window=9)
        df["EMA21"] = ta.trend.ema_indicator(df["close"], window=21)

        df["RSI"] = ta.momentum.rsi(df["close"], window=14)

        dmi = ta.trend.ADXIndicator(
            df["high"],
            df["low"],
            df["close"],
            window=14
        )

        df["+DI"] = dmi.adx_pos()
        df["-DI"] = dmi.adx_neg()

        df["DX"] = (abs(df["+DI"] - df["-DI"]) /
                   (df["+DI"] + df["-DI"])) * 100

        df = add_supertrend(df)

        log_rows = build_hourly_log(df)

        write_full_hourly_log(log_rows)

        last = df.iloc[-2]

    except Exception as exc:

        app.logger.warning(f"Fallback data: {exc}")

        return (
            0,0,0,0,0,0,0,0,0,0,0,False,0,
            "RANGE","orange","Data unavailable"
        )

    price = round(last["close"], 2)
    open_price = round(last["open"], 2)
    high_price = round(last["high"], 2)
    low_price = round(last["low"], 2)
    close_price = round(last["close"], 2)

    ema9 = round(last["EMA9"], 2)
    ema21 = round(last["EMA21"], 2)
    rsi = round(last["RSI"], 2)

    di_plus = round(last["+DI"], 2)
    di_minus = round(last["-DI"], 2)

    dx = round(last["DX"], 2)

    supertrend_bull = last["Trend"]
    supertrend_value = round(last["Supertrend"], 2)

    if di_plus > di_minus and dx > 20 and supertrend_bull:

        trend = "BULLISH"
        color = "green"
        strategy = "Bull Put Spread / Bull Call Spread"

    elif di_minus > di_plus and dx > 20 and not supertrend_bull:

        trend = "BEARISH"
        color = "red"
        strategy = "Bear Call Spread / Bear Put Spread"

    else:

        trend = "RANGE"
        color = "orange"
        strategy = "Iron Condor / Short Strangle"
        
    # -------------------------------------
    # OPTION ENGINE (runs after trend set)
    # -------------------------------------

    #option_chain = get_option_chain()

    #spread = build_strategy(option_chain, trend)
    
    # SAFE FORMAT
    #if spread is None:
    #    spread_text = "No valid spread found"
    #else:
    #    spread_text = format_strategy(spread)

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
        strategy
    )


def hourly_updater():

    while True:

        try:

            now = get_ist_now()

            if now.minute == 2:

                app.logger.info("Running hourly market update")

                get_market_direction()

                time.sleep(70)

        except Exception as e:

            app.logger.warning(f"Hourly updater error: {e}")

        time.sleep(20)


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
        strategy
    ) = get_market_direction()

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
        suggested_strategy=strategy,
        log_records=log_records
    )


if __name__ == "__main__":

    thread = threading.Thread(target=hourly_updater)
    thread.daemon = True
    thread.start()

    app.run(host="0.0.0.0", port=10000)