
from openalgo import api

API_KEY = "49fcd9b789b66eb442c14068c59160353302646b4acf43a5ce9992edb5ba0b7c"
HOST = "http://127.0.0.1:5000"

client = api(api_key=API_KEY, host=HOST)

def get_option_greeks(symbol, underlying="NIFTY"):
    try:
        response = client.optiongreeks(
            symbol=symbol,
            exchange="NFO",
            interest_rate=0.06,   # better than 0.00
            underlying_symbol=underlying,
            underlying_exchange="NSE_INDEX"
        )

        # 🔍 Adjust keys based on actual response
        return {
            "delta": response.get("delta", 0),
            "gamma": response.get("gamma", 0),
            "theta": response.get("theta", 0),
            "vega": response.get("vega", 0),
        }

    except Exception as e:
        print(f"Greek fetch error for {symbol}: {e}")
        return None