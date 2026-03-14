"""
Kotak Option Chain Fetcher
--------------------------

Fetch option chain for NIFTY from Kotak Neo API
and convert into format required by option_engine.py
"""

import datetime
import requests
# If using Kotak Neo Python SDK
# install: pip install neo-api-client
from neo_api_client import NeoAPI



# ---------------------------------
# CONFIGURATION
# ---------------------------------

CLIENT_ID = "YOUR_CLIENT_ID"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"


# ---------------------------------
# CONNECT TO KOTAK
# ---------------------------------

def get_kotak_client():

    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }

    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers)

    data = session.get(url, headers=headers).json()

    return data


# ---------------------------------
# FIND NEAREST WEEKLY EXPIRY
# ---------------------------------

def get_nearest_expiry(expiry_list):

    today = datetime.date.today()

    expiry_dates = [
        datetime.datetime.strptime(e, "%d-%b-%Y").date()
        for e in expiry_list
    ]

    future_expiries = [e for e in expiry_dates if e >= today]

    nearest = min(future_expiries)

    return nearest.strftime("%d-%b-%Y")


# ---------------------------------
# FETCH OPTION CHAIN
# ---------------------------------

def fetch_option_chain():

    client = get_kotak_client()

    response = client.get_option_chain(
        exchange_segment="nse_fo",
        instrument="OPTIDX",
        symbol="NIFTY"
    )

    data = response.get("data", [])

    return data


# ---------------------------------
# FORMAT OPTION CHAIN
# ---------------------------------

def format_option_chain(raw_chain):

    formatted = []

    for item in raw_chain:

        try:

            strike = float(item["strike_price"])

            option_type = item["option_type"]

            delta = float(item["delta"])

            formatted.append({
                "strike": strike,
                "type": option_type,
                "delta": delta
            })

        except Exception:

            continue

    return formatted


# ---------------------------------
# MAIN FUNCTION
# ---------------------------------

def get_kotak_option_chain():

    raw_chain = fetch_option_chain()

    option_chain = format_option_chain(raw_chain)

    return option_chain