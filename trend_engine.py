from data_fetch import fetch_data
from indicators import add_indicators, add_supertrend
import ta
import datetime

last_cache = {}
last_updated = {}

def get_ist_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)


def get_market_direction(symbol="NIFTY", exchange="NSE"):

    now = get_ist_now()

    if symbol in last_cache and (now - last_updated[symbol]).seconds < 300:
        return last_cache[symbol]

    try:
        df_h, df_d = fetch_data(symbol, exchange)

        # Hourly
        df_h = add_indicators(df_h)
        df_h = add_supertrend(df_h)

        # Daily
        df_d["EMA9"] = ta.trend.ema_indicator(df_d["close"], window=9)
        df_d["EMA21"] = ta.trend.ema_indicator(df_d["close"], window=21)
        df_d = add_supertrend(df_d)

        last_h = df_h.iloc[-1]
        last_d = df_d.iloc[-1]

        price = round(last_h["close"], 2)
        dx = round(last_h["DX"], 2)
        di_plus = round(last_h["+DI"], 2)
        di_minus = round(last_h["-DI"], 2)

        # Trend logic
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

        daily_trend = "BULLISH" if last_d["Trend"] else "BEARISH"
        hourly_trend = "BULLISH" if last_h["Trend"] else "BEARISH"
        alignment = "ALIGNED" if daily_trend == hourly_trend else "CONFLICT"

        rsi = round(ta.momentum.rsi(df_h["close"], window=14).iloc[-1], 2)

        result = (
            price,
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