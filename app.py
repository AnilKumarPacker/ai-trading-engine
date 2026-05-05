from flask import Flask, render_template, request
from trend_engine import get_market_direction
from option_engine import SimpleOptionChain, select_strikes


app = Flask(__name__)

@app.route("/")
def dashboard():

    symbol = request.args.get("symbol", "NIFTY")

    (
        price, ema9, ema21, rsi,
        di_plus, di_minus, dx,
        supertrend_bull,
        trend, color, strategy,
        daily_trend, hourly_trend, alignment
    ) = get_market_direction(symbol)

    option_chain = SimpleOptionChain(underlying=symbol).get_option_chain()
    print("opton chain", option_chain)
    option_strategy = select_strikes(option_chain, trend)
    

    return render_template(
        "dashboard.html",
        symbol=symbol,
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
        option_strategy=option_strategy
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)