import hashlib
import sys
sys.path.insert(0, r'E:\github\Python\ai-trading-engine\ShoonyaApi-py-master')
import pyotp  

from api_helper import ShoonyaApiPy

TOTP_SECRET = '3B3SVF64J6FW64E5VZG7MZR6QA2EEDJA'

api = ShoonyaApiPy()

print(api)
USER_ID      = 'FA22481'
PASSWORD     = hashlib.sha256('Shoonya123!'.encode()).hexdigest()
TOTP_SECRET  = '3B3SVF64J6FW64E5VZG7MZR6QA2EEDJA'
VENDOR_CODE  = 'FA22481_U'
API_KEY      = hashlib.sha256('411101f303b9e5c264f1a6e0a5429c66'.encode()).hexdigest()
IMEI         = 'abc1234'

ret = api.login(
    userid=USER_ID,
    password=PASSWORD,
    twoFA=pyotp.TOTP(TOTP_SECRET).now(),
    vendor_code=VENDOR_CODE,
    api_secret=API_KEY,
    imei=IMEI
)
print(ret)