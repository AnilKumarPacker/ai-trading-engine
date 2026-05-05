from tvDatafeed import TvDatafeed, Interval
import pandas as pd

tv = TvDatafeed(
    username="hanumanthmaster1950",
    password="Tradingview123@"
)

def fetch_data(symbol, exchange="NSE"):
    df_h = tv.get_hist(symbol=symbol, exchange=exchange,
                       interval=Interval.in_1_hour, n_bars=300)

    df_d = tv.get_hist(symbol=symbol, exchange=exchange,
                       interval=Interval.in_daily, n_bars=200)

    df_h = pd.DataFrame(df_h)
    df_d = pd.DataFrame(df_d)

    if df_h.empty or df_d.empty:
        raise ValueError("No data")

    return df_h, df_d