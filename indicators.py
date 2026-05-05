import ta

def add_indicators(df):
    df["EMA9"] = ta.trend.ema_indicator(df["close"], window=9)
    df["EMA21"] = ta.trend.ema_indicator(df["close"], window=21)

    dmi = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["+DI"] = dmi.adx_pos()
    df["-DI"] = dmi.adx_neg()
    df["DX"] = (abs(df["+DI"] - df["-DI"]) / (df["+DI"] + df["-DI"])) * 100

    return df


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