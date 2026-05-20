from __future__ import annotations

import math
import os
import re
from datetime import datetime

import pytz
import requests

HOST = os.getenv("OPENALGO_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
API_KEY = os.getenv(
    "OPENALGO_API_KEY",
    "f0ebb94e9752aebf83c7723a1cef2a0a4252782c09a66b67740cc24a654c433b",
)

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d-%b-%y",
    "%d-%B-%y",
    "%d%b%y",
    "%d%b%Y",
)

INDEX_CONFIG = {
    "NIFTY": {
        "expiry_exchange": "NFO",
        "optionchain_exchange": "NSE_INDEX",
        "spot_env": "NIFTY_SPOT",
    },
    "BANKNIFTY": {
        "expiry_exchange": "NFO",
        "optionchain_exchange": "NSE_INDEX",
        "spot_env": "BANKNIFTY_SPOT",
    },
    "SENSEX": {
        "expiry_exchange": "BFO",
        "optionchain_exchange": "BSE_INDEX",
        "spot_env": "SENSEX_SPOT",
    },
}


def parse_expiry_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None

    value = value.strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            pass
    return None


def format_expiry_date(value: str) -> str:
    expiry = parse_expiry_date(value)
    if expiry is None:
        return value.strip().upper()
    return expiry.strftime("%d%b%y").upper()


def nearest_date_from_response(response_json: object) -> str | None:
    if isinstance(response_json, dict):
        dates = response_json.get("data", [])
    else:
        dates = response_json

    if not isinstance(dates, list):
        return None

    parsed_dates = [parsed for item in dates if (parsed := parse_expiry_date(item))]
    if not parsed_dates:
        return None

    today = datetime.now().date()
    future_dates = [d for d in parsed_dates if d.date() >= today]
    nearest = min(future_dates if future_dates else parsed_dates)
    return nearest.strftime("%d%b%y").upper()


def parse_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def symbols_from_response(response_json: object) -> list[str]:
    symbols: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, dict):
            symbol = value.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                symbols.append(symbol.strip())

            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(response_json)
    return list(dict.fromkeys(symbols))


def option_data_from_response(response_json: object) -> dict[str, dict]:
    option_data: dict[str, dict] = {}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            symbol = value.get("symbol")
            if isinstance(symbol, str) and symbol.strip():
                option_data[symbol.strip()] = value

            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(response_json)
    return option_data


def atm_strike_from_response(response_json: object) -> float | None:
    def collect(value: object) -> float | None:
        if isinstance(value, dict):
            for key in ("atm_strike", "atm", "spot", "spot_price", "underlying_ltp"):
                found = parse_float(value.get(key))
                if found is not None:
                    return found

            for item in value.values():
                found = collect(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = collect(item)
                if found is not None:
                    return found

        return None

    return collect(response_json)


def parse_option_symbol(
    symbol: str,
    expiry_date: str,
    underlying: str,
) -> tuple[float, str] | None:
    pattern = (
        rf"^{re.escape(underlying)}"
        rf"{re.escape(expiry_date)}"
        rf"(\d+(?:\.\d+)?)(CE|PE)$"
    )
    match = re.match(pattern, symbol.upper())
    if not match:
        return None

    strike = float(match.group(1))
    option_type = match.group(2)
    return strike, option_type


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def calculate_delta(
    spot_price: float,
    strike_price: float,
    expiry: datetime,
    option_type: str,
    volatility: float = 0.15,
    risk_free_rate: float = 0.07,
) -> float | None:
    days_to_expiry = max((expiry.date() - datetime.now().date()).days, 1)
    years_to_expiry = days_to_expiry / 365.0

    if spot_price <= 0 or strike_price <= 0 or volatility <= 0:
        return None

    d1 = (
        math.log(spot_price / strike_price)
        + (risk_free_rate + 0.5 * volatility**2) * years_to_expiry
    ) / (volatility * math.sqrt(years_to_expiry))

    if option_type == "CE":
        return round(normal_cdf(d1), 4)
    return round(normal_cdf(d1) - 1.0, 4)


def _market_value(data: dict, keys: tuple[str, ...], default: float = 0) -> float:
    for key in keys:
        value = parse_float(data.get(key))
        if value is not None:
            return value
    return default


class SimpleOptionChain:
    def __init__(
        self,
        underlying: str = "NIFTY",
        expiry: str | None = None,
        api_key: str | None = None,
        host: str | None = None,
        strike_count: int = 30,
    ):
        self.underlying = underlying.upper()
        self.config = INDEX_CONFIG.get(
            self.underlying,
            {
                "expiry_exchange": "NFO",
                "optionchain_exchange": "NSE_INDEX",
                "spot_env": f"{self.underlying}_SPOT",
            },
        )
        self.expiry = format_expiry_date(expiry) if expiry else None
        self.api_key = api_key or API_KEY
        self.host = (host or HOST).rstrip("/")
        self.strike_count = strike_count

    @property
    def expiry_url(self) -> str:
        return f"{self.host}/api/v1/expiry"

    @property
    def optionchain_url(self) -> str:
        return f"{self.host}/api/v1/optionchain"

    def get_expiry(self) -> str:
        payload = {
            "apikey": self.api_key,
            "symbol": self.underlying,
            "exchange": self.config["expiry_exchange"],
            "instrumenttype": "options",
        }

        response_json = self._post_json(self.expiry_url, payload)
        nearest_expiry = nearest_date_from_response(response_json)
        if not nearest_expiry:
            raise ValueError(f"No expiry found for {self.underlying}: {response_json}")

        self.expiry = nearest_expiry
        return nearest_expiry

    def get_option_chain(self) -> dict:
        expiry = self.expiry or self.get_expiry()
        payload = {
            "apikey": self.api_key,
            "underlying": self.underlying,
            "exchange": self.config["optionchain_exchange"],
            "expiry_date": expiry,
            "strike_count": self.strike_count,
        }

        response_json = self._post_json(self.optionchain_url, payload)
        symbols = symbols_from_response(response_json)
        if not symbols:
            raise ValueError(f"No option symbols found for {self.underlying}: {response_json}")

        spot_price = (
            atm_strike_from_response(response_json)
            or parse_float(os.getenv("UNDERLYING_PRICE"))
            or parse_float(os.getenv(self.config["spot_env"]))
        )
        if spot_price is None:
            raise ValueError(
                "atm_strike not found in option chain response. "
                f"Set UNDERLYING_PRICE or {self.config['spot_env']} "
                "to calculate the option chain."
            )

        expiry_date = parse_expiry_date(expiry)
        option_data = option_data_from_response(response_json)
        chain = self._build_chain(
            symbols=symbols,
            option_data=option_data,
            expiry=expiry,
            expiry_date=expiry_date,
            spot_price=spot_price,
        )

        return {
            "underlying": self.underlying,
            "expiry": expiry,
            "spot_price": spot_price,
            "atm_strike": min(
                (row["strike"] for row in chain),
                key=lambda strike: abs(strike - spot_price),
            ),
            "timestamp": datetime.now(pytz.timezone("Asia/Kolkata")).isoformat(),
            "raw": response_json,
            "chain": chain,
        }

    def _post_json(self, url: str, payload: dict) -> object:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=20)

        if response.status_code == 403:
            raise PermissionError("OpenAlgo API key is invalid for this instance.")
        response.raise_for_status()
        return response.json()

    def _build_chain(
        self,
        symbols: list[str],
        option_data: dict[str, dict],
        expiry: str,
        expiry_date: datetime | None,
        spot_price: float,
    ) -> list[dict]:
        by_strike: dict[float, dict[str, dict]] = {}

        for symbol in symbols:
            parsed_symbol = parse_option_symbol(symbol, expiry, self.underlying)
            if parsed_symbol is None:
                continue

            strike, option_type = parsed_symbol
            data = option_data.get(symbol, {})
            option = self._format_option(
                symbol=symbol,
                data=data,
                strike=strike,
                option_type=option_type,
                expiry_date=expiry_date,
                spot_price=spot_price,
            )
            by_strike.setdefault(strike, {})[option_type] = option

        if not by_strike:
            raise ValueError("Option symbols were returned but could not be parsed.")

        strikes = sorted(by_strike)
        atm_strike = min(strikes, key=lambda strike: abs(strike - spot_price))
        atm_index = strikes.index(atm_strike)
        start = max(0, atm_index - self.strike_count)
        end = min(len(strikes), atm_index + self.strike_count + 1)

        chain: list[dict] = []
        for strike in strikes[start:end]:
            row = by_strike[strike]
            chain.append(
                {
                    "strike": strike,
                    "ce": row.get("CE", {}),
                    "pe": row.get("PE", {}),
                }
            )

        return chain

    def _format_option(
        self,
        symbol: str,
        data: dict,
        strike: float,
        option_type: str,
        expiry_date: datetime | None,
        spot_price: float,
    ) -> dict:
        delta = None
        if expiry_date is not None:
            delta = calculate_delta(
                spot_price=spot_price,
                strike_price=strike,
                expiry=expiry_date,
                option_type=option_type,
                volatility=_market_value(data, ("iv", "implied_volatility"), 0.15),
                risk_free_rate=0.07,
            )

        return {
            "symbol": symbol,
            "strike": strike,
            "type": option_type,
            "ltp": _market_value(data, ("ltp", "lp", "last_price")),
            "volume": _market_value(data, ("volume", "v", "vol")),
            "delta": delta,
            "raw": data,
        }


def normalize_option_chain(chain_json: dict) -> list[dict]:
    normalized = []

    for item in chain_json.get("chain", []):
        strike = item["strike"]

        for option_type, key in (("CE", "ce"), ("PE", "pe")):
            option = item.get(key) or {}
            normalized.append(
                {
                    "strike": strike,
                    "type": option_type,
                    "symbol": option.get("symbol"),
                    "ltp": option.get("ltp", 0),
                    "volume": option.get("volume", 0),
                    "delta": option.get("delta"),
                }
            )

    return normalized


def _delta_value(option: dict) -> float | None:
    delta = parse_float(option.get("delta"))
    if delta is None:
        return None

    # Some APIs report delta as 20 instead of 0.20. Normalize to decimal.
    if abs(delta) > 1:
        delta = delta / 100
    return delta


def _select_20_delta(options: list[dict]) -> dict | None:
    with_delta = [
        (option, abs(delta))
        for option in options
        if (delta := _delta_value(option)) is not None
    ]
    if not with_delta:
        return None

    fair = [
        (option, delta)
        for option, delta in with_delta
        if 0.20 <= delta <= 0.21
    ]
    candidates = fair or with_delta
    return min(candidates, key=lambda item: abs(item[1] - 0.20))[0]


def _protection_500_points_away(options: list[dict], sell: dict, direction: str) -> dict | None:
    if not sell:
        return None

    if direction == "lower":
        candidates = [
            option
            for option in options
            if option["strike"] <= sell["strike"] - 500
        ]
        return max(candidates, key=lambda x: x["strike"], default=None)

    candidates = [
        option
        for option in options
        if option["strike"] >= sell["strike"] + 500
    ]
    return min(candidates, key=lambda x: x["strike"], default=None)


def select_strikes(chain_json: dict, trend: str) -> dict:
    try:
        atm = chain_json["atm_strike"]
        options = normalize_option_chain(chain_json)

        ce = [o for o in options if o["type"] == "CE"]
        pe = [o for o in options if o["type"] == "PE"]

        if trend == "BULLISH":
            otm_pe = [o for o in pe if o["strike"] < atm]
            sell = _select_20_delta(otm_pe)
            buy = _protection_500_points_away(otm_pe, sell, "lower")

            return {
                "strategy": "Bull Put Spread",
                "sell": sell,
                "buy": buy,
            }

        if trend == "BEARISH":
            otm_ce = [o for o in ce if o["strike"] > atm]
            sell = _select_20_delta(otm_ce)
            buy = _protection_500_points_away(otm_ce, sell, "higher")

            return {
                "strategy": "Bear Call Spread",
                "sell": sell,
                "buy": buy,
            }

        otm_ce = [o for o in ce if o["strike"] > atm]
        otm_pe = [o for o in pe if o["strike"] < atm]
        sell_ce = _select_20_delta(otm_ce)
        sell_pe = _select_20_delta(otm_pe)

        return {
            "strategy": "Iron Condor",
            "sell_ce": sell_ce,
            "buy_ce": _protection_500_points_away(otm_ce, sell_ce, "higher"),
            "sell_pe": sell_pe,
            "buy_pe": _protection_500_points_away(otm_pe, sell_pe, "lower"),
        }

    except Exception as e:
        return {"strategy": "Error", "error": str(e)}


if __name__ == "__main__":
    import json

    oc = SimpleOptionChain(underlying="NIFTY")
    data = oc.get_option_chain()
    print(json.dumps(data, indent=2))
