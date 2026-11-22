"""HMAC signing for explicitly configured Binance test endpoints."""
import hashlib
import hmac
import time
from urllib.parse import urlencode


def sign_request(req, headers, params):
    key, secret = req.get('auth_api_key'), req.get('auth_api_secret')
    if not key or not secret or any(marker in str(value) for value in (key, secret) for marker in ('{{', '${')):
        raise ValueError('币安 HMAC 需要测试环境中的 API Key 和 API Secret 引用')
    params = dict(params)
    params.setdefault('timestamp', int(time.time() * 1000))
    params.setdefault('recvWindow', 5000)
    params.pop('signature', None)
    encoded = urlencode(params, doseq=True)
    params['signature'] = hmac.new(str(secret).encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return {**headers, 'X-MBX-APIKEY': key}, params, None
