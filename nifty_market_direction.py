from flask import Flask, render_template
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import ta

app = Flask(__name__)

tv = TvDatafeed()

def get_market_direction():

    data = tv.get_hist(
        symbol='NIFTY',
        exchange='NSE',
        interval=Interval.in_15_minute,
        n_bars=200
    )

    df = pd.DataFrame(data)

    df["EMA20"] = ta.trend.ema_indicator(df["close"], window=20)
    df["EMA50"] = ta.trend.ema_indicator(df["close"], window=50)
    df["RSI"] = ta.momentum.rsi(df["close"], window=14)

    last = df.iloc[-1]

    price = round(last["close"],2)
    ema20 = round(last["EMA20"],2)
    ema50 = round(last["EMA50"],2)
    rsi = round(last["RSI"],2)

    if price > ema20 and ema20 > ema50 and rsi > 55:
        trend = "BULLISH"
        color = "green"
    elif price < ema20 and ema20 < ema50 and rsi < 45:
        trend = "BEARISH"
        color = "red"
    else:
        trend = "RANGE"
        color = "orange"

    return price, ema20, ema50, rsi, trend, color


@app.route("/")
def dashboard():

    price, ema20, ema50, rsi, trend, color = get_market_direction()

    return render_template(
        "dashboard.html",
        price=price,
        ema20=ema20,
        ema50=ema50,
        rsi=rsi,
        trend=trend,
        color=color
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)