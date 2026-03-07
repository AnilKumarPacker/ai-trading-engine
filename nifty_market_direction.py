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
        interval=Interval.in_1_hour,
        n_bars=200
    )

    df = pd.DataFrame(data)

    # EMA + RSI
    df["EMA9"] = ta.trend.ema_indicator(df["close"], window=9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], window=21)
    df["RSI"] = ta.momentum.rsi(df["close"], window=14)

    # DMI calculation
    dmi = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["+DI"] = dmi.adx_pos()
    df["-DI"] = dmi.adx_neg()

    # DX calculation
    df["DX"] = (abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])) * 100

    last = df.iloc[-1]

    price = round(last["close"], 2)
    ema9 = round(last["EMA9"], 2)
    ema21 = round(last["EMA21"], 2)
    rsi = round(last["RSI"], 2)
    di_plus = round(last["+DI"], 2)
    di_minus = round(last["-DI"], 2)
    dx = round(last["DX"], 2)

    # Directional bias logic
    if di_plus > di_minus and dx > 20:
        trend = "BULLISH"
        color = "green"
        suggested_strategy = "Bull Put Spread / Bull Call Spread"

    elif di_minus > di_plus and dx > 20:
        trend = "BEARISH"
        color = "red"
        suggested_strategy = "Bear Call Spread / Bear Put Spread"

    else:
        trend = "RANGE"
        color = "orange"
        suggested_strategy = "Iron Condor / Short Strangle"

    return price, ema9, ema21, rsi, di_plus, di_minus, dx, trend, color, suggested_strategy


@app.route("/")
def dashboard():

    price, ema9, ema21, rsi, di_plus, di_minus, dx, trend, color, suggested_strategy = get_market_direction()

    return render_template(
        "dashboard.html",
        price=price,
        ema9=ema9,
        ema21=ema21,
        rsi=rsi,
        di_plus=di_plus,
        di_minus=di_minus,
        dx=dx,
        trend=trend,
        color=color,
        suggested_strategy=suggested_strategy
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)