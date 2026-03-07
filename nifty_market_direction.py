# nifty_market_direction.py

from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta
import time

def fetch_nifty_data():

    tv = TvDatafeed()

    data = tv.get_hist(
        symbol='NIFTY',
        exchange='NSE',
        interval=Interval.in_15_minute,
        n_bars=200
    )

    return data


def calculate_indicators(df):

    df["EMA20"] = ta.trend.ema_indicator(df["close"], window=20)
    df["EMA50"] = ta.trend.ema_indicator(df["close"], window=50)
    df["RSI"] = ta.momentum.rsi(df["close"], window=14)

    return df


def determine_market_direction(df):

    last = df.iloc[-1]

    price = last["close"]
    ema20 = last["EMA20"]
    ema50 = last["EMA50"]
    rsi = last["RSI"]

    if price > ema20 and ema20 > ema50 and rsi > 55:
        direction = "BULLISH"

    elif price < ema20 and ema20 < ema50 and rsi < 45:
        direction = "BEARISH"

    else:
        direction = "RANGE"

    return {
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "direction": direction
    }


def print_summary(result):

    print("\n-------- NIFTY MARKET ANALYSIS --------")
    print(f"Current Price : {result['price']:.2f}")
    print(f"EMA 20        : {result['ema20']:.2f}")
    print(f"EMA 50        : {result['ema50']:.2f}")
    print(f"RSI           : {result['rsi']:.2f}")
    print(f"Market Trend  : {result['direction']}")
    print("---------------------------------------\n")


def main():

    print("Fetching NIFTY data...")

    df = fetch_nifty_data()

    if df is None or df.empty:
        print("Failed to fetch data")
        return

    df = calculate_indicators(df)

    result = determine_market_direction(df)

    print_summary(result)


if __name__ == "__main__":
    while True:
        main()
        time.sleep(900)   # run every 15 minutes