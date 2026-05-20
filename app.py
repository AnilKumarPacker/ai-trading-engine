import datetime

from flask import Flask, render_template, request
from trend_engine import get_market_direction
from option_engine import SimpleOptionChain, select_strikes


app = Flask(__name__)
SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
TREND_EXCHANGES = {
    "SENSEX": "BSE",
}


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


@app.route("/")
def dashboard():

    symbol = request.args.get("symbol", "NIFTY").upper()
    if symbol not in SYMBOLS:
        symbol = "NIFTY"
    trend_exchange = TREND_EXCHANGES.get(symbol, "NSE")

    (
        price, ema9, ema21, rsi,
        di_plus, di_minus, dx,
        supertrend_bull,
        trend, color, strategy,
        daily_trend, hourly_trend, alignment
    ) = get_market_direction(symbol, exchange=trend_exchange)

    option_chain = SimpleOptionChain(underlying=symbol).get_option_chain()
    option_strategy = select_strikes(option_chain, trend)
    dashboard_signals = build_dashboard_signals(trend, alignment, dx, rsi)
    updated_at = get_ist_now().strftime("%d %b %Y, %I:%M %p IST")
    

    return render_template(
        "dashboard.html",
        symbol=symbol,
        symbols=SYMBOLS,
        updated_at=updated_at,
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
        option_chain=option_chain,
        option_strategy=option_strategy,
        **dashboard_signals
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
