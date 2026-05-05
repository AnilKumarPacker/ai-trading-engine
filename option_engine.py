import logging
from datetime import datetime
import pytz
from openalgo_service import get_option_greeks
# Replace this with your actual OpenAlgo client import
from openalgo import api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
API_KEY = "49fcd9b789b66eb442c14068c59160353302646b4acf43a5ce9992edb5ba0b7c"
HOST = "http://127.0.0.1:5000"

class SimpleOptionChain:
    def __init__(self, underlying="NIFTY", expiry=None):
        self.client = api(api_key=API_KEY, host=HOST)
        self.underlying = underlying
        self.expiry = expiry
        self.strike_step = 50 if underlying == "NIFTY" else 100
        self.atm = 0
        self.option_chain = []

    
    # 🔹 Step 1: Auto-fetch nearest expiry
    def get_expiry(self):
        exchange = "BFO" if self.underlying == "SENSEX" else "NFO"

        res = self.client.expiry(
            symbol=self.underlying,
            exchange=exchange,
            instrumenttype="options"
        )

        if res.get("status") == "success":
            expiries = res.get("data", [])
            if expiries:
                self.expiry = expiries[0]   # nearest expiry
                return self.expiry

        raise Exception("Failed to fetch expiry")

    def get_spot_price(self):
        exchange = "BSE_INDEX" if self.underlying == "SENSEX" else "NSE_INDEX"

        res = self.client.quotes(symbol=self.underlying, exchange=exchange)

        if res.get("status") == "success":
            return res["data"]["ltp"]

        raise Exception("Failed to fetch spot price")

    def calculate_atm(self, ltp):
        return round(ltp / self.strike_step) * self.strike_step

    def generate_strikes(self):
        strikes = []

        for i in range(-10, 11):  # 10 ITM + ATM + 10 OTM
            strike = self.atm + i * self.strike_step
            strikes.append(strike)

        return strikes

    def format_expiry(self):
        # Converts "28-AUG-25" → "28AUG"
        parts = self.expiry.split("-")
        return f"{parts[0]}{parts[1]}{parts[2]}".upper()

    def build_symbol(self, strike, option_type):
        expiry_fmt = self.format_expiry()
        return f"{self.underlying}{expiry_fmt}{int(strike)}{option_type}"
    
    def get_option_chain(self):

        if not self.expiry:
            self.expiry = self.get_expiry()

        chain = self.client.optionchain(
            underlying=self.underlying,
            exchange="NSE_INDEX",
            expiry_date=self.format_expiry(),
            strike_count=10
        )

        return chain


    def get_option_chain_old(self):
        if not self.expiry:
            self.expiry = self.get_expiry()
        
        ltp = self.get_spot_price()
        self.atm = self.calculate_atm(ltp)

        strikes = self.generate_strikes()

        exchange = "BFO" if self.underlying == "SENSEX" else "NFO"

        chain = []

        for strike in strikes:
            ce_symbol = self.build_symbol(strike, "CE")
            pe_symbol = self.build_symbol(strike, "PE")
            
            ce_data = self.client.quotes(symbol=ce_symbol, exchange=exchange)
            pe_data = self.client.quotes(symbol=pe_symbol, exchange=exchange)

            chain.append({
                "strike": strike,
                "CE": ce_data.get("data", {}),
                "PE": pe_data.get("data", {})
            })

        return {
            "underlying": self.underlying,
            "ltp": ltp,
            "atm": self.atm,
            "expiry": self.expiry,
            "timestamp": datetime.now(pytz.timezone("Asia/Kolkata")).isoformat(),
            "data": chain
        }
    
    # option_engine.py

def normalize_option_chain(chain_json):
    normalized = []

    for item in chain_json["chain"]:
        strike = item["strike"]

        ce = item["ce"]
        pe = item["pe"]

        normalized.append({
            "strike": strike,
            "type": "CE",
            "ltp": ce.get("ltp", 0),
            "volume": ce.get("volume", 0)
        })

        normalized.append({
            "strike": strike,
            "type": "PE",
            "ltp": pe.get("ltp", 0),
            "volume": pe.get("volume", 0)
        })

    return normalized


# -------------------------
# STRIKE SELECTION LOGIC
# -------------------------
def select_strikes(chain_json, trend):

    try:
        atm = chain_json["atm_strike"]
        options = normalize_option_chain(chain_json)

        ce = [o for o in options if o["type"] == "CE"]
        pe = [o for o in options if o["type"] == "PE"]
        print("CE is ", ce)
        print("PE is ", pe)

        if trend == "BULLISH":

            otm_pe = [o for o in pe if o["strike"] < atm]
            filtered = [o for o in otm_pe if 70 <= o["ltp"] <= 150]

            sorted_pe = sorted(filtered, key=lambda x: x["volume"], reverse=True)

            sell = sorted_pe[0]
            buy = next(o for o in otm_pe if o["strike"] < sell["strike"])

            return {
                "strategy": "Bull Put Spread",
                "sell": sell,
                "buy": buy
            }

        elif trend == "BEARISH":

            otm_ce = [o for o in ce if o["strike"] > atm]
            filtered = [o for o in otm_ce if 70 <= o["ltp"] <= 150]

            sorted_ce = sorted(filtered, key=lambda x: x["volume"], reverse=True)

            sell = sorted_ce[0]
            buy = next(o for o in otm_ce if o["strike"] > sell["strike"])

            return {
                "strategy": "Bear Call Spread",
                "sell": sell,
                "buy": buy
            }

        else:

            otm_ce = [o for o in ce if o["strike"] > atm]
            otm_pe = [o for o in pe if o["strike"] < atm]
            print("otm_ce ",otm_ce)
            print("otm_pe ",otm_pe) 
            ce_sorted = sorted(otm_ce, key=lambda x: x["volume"], reverse=True)
            pe_sorted = sorted(otm_pe, key=lambda x: x["volume"], reverse=True)
            print("ce_sorted ",ce_sorted)
            print("pe_sorted ",pe_sorted) 

            return {
                "strategy": "Iron Condor",
                "sell_ce": ce_sorted[0],
                "sell_pe": pe_sorted[0]
            }

    except Exception as e:
        print("Option Engine Error:", e)
        return {"strategy": "Error"}

# ================= RUN =================



def calculate_delta(spot, strike, expiry_date, option_type, iv=0.15, r=0.06):
    """
    spot        - current Nifty LTP
    strike      - option strike price
    expiry_date - datetime object of expiry
    option_type - 'c' for CE, 'p' for PE
    iv          - implied volatility (use 0.15 as default, or fetch from chain)
    r           - risk-free rate
    """
    today = datetime.now(pytz.timezone("Asia/Kolkata")).replace(tzinfo=None)
    t = (expiry_date - today).days / 365.0

    if t <= 0:
        return None

    flag = 'c' if option_type == 'CE' else 'p'

    try:
        d = delta(flag, spot, strike, t, r, iv)
        return round(d, 4)
    except Exception as e:
        return None

if __name__ == "__main__":
    API_KEY = "49fcd9b789b66eb442c14068c59160353302646b4acf43a5ce9992edb5ba0b7c"
    HOST = "http://127.0.0.1:5000"

    oc = SimpleOptionChain(API_KEY, HOST, underlying="NIFTY")

    data = oc.get_option_chain()

    import json
    print(json.dumps(data, indent=2))