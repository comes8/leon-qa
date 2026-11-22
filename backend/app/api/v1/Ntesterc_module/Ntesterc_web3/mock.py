"""Loopback-only synthetic trading fixtures. Every scenario creates an isolated session."""
from decimal import Decimal, InvalidOperation
from time import monotonic
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()
_sessions: dict = {}


@router.api_route('/sessions', methods=['POST'])
async def create_session(request: Request):
    require_local(request)
    expired = [key for key, value in _sessions.items() if monotonic() - value['created'] > 7200]
    for key in expired:
        _sessions.pop(key, None)
    if len(_sessions) >= 1000:
        raise HTTPException(429, '模拟会话已满，请清理旧会话')
    key = uuid4().hex
    _sessions[key] = {'created': monotonic(), 'orders': {}, 'transfers': {}, 'receipts': {},
                      'free': Decimal('1000'), 'locked': Decimal('0'), 'position': Decimal('5'),
                      'wallet': Decimal('100'), 'futures_wallet': Decimal('0'), 'spot_events': []}
    return JSONResponse({'session_id': key, 'environment': 'local_mock'}, status_code=201)


def require_local(request):
    if request.client is None or request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        raise HTTPException(403, '模拟接口限本机访问')


def session(request, session_id):
    require_local(request)
    if session_id not in _sessions:
        raise HTTPException(404, '模拟会话不存在或已过期')
    return _sessions[session_id]


@router.delete('/{sid}/session')
async def delete_session(sid: str, request: Request):
    session(request, sid)
    _sessions.pop(sid)
    return {'session_id': sid, 'deleted': True, 'scope': 'local_synthetic_only'}


def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError
        return result
    except (InvalidOperation, ValueError):
        raise HTTPException(400, 'INVALID_AMOUNT')


def amount(value):
    return format(value.quantize(Decimal('0.00000001')), 'f')


def order_view(order_id, order):
    return {'orderId': order_id, 'status': order['status'], 'origQty': amount(order['quantity']),
            'executedQty': amount(order['filled']), 'remainingFrozen': amount(order['locked']),
            'canceledQty': amount(order['quantity'] - order['filled'] if order['status'] == 'CANCELED' else Decimal('0')),
            'activeRemainingQty': amount(order['quantity'] - order['filled'] if order['status'] in {'NEW', 'PARTIALLY_FILLED'} else Decimal('0'))}


def spot_event(state, oid, kind, value):
    identity = uuid4().hex
    state.setdefault('spot_events', []).append({'eventId': identity, 'orderId': oid, 'kind': kind,
        'amount': amount(value), 'asset': 'QUOTE', 'freeAfter': amount(state['free']), 'lockedAfter': amount(state['locked'])})
    return identity


@router.get('/{sid}/spot/balances')
async def spot_balances(sid: str, request: Request):
    state = session(request, sid)
    return {'asset': 'QUOTE', 'free': amount(state['free']), 'locked': amount(state['locked']), 'profile': 'local-synthetic-spot-v1'}


@router.get('/{sid}/spot/events/{oid}')
async def spot_events(sid: str, oid: str, request: Request):
    state = session(request, sid)
    if oid not in state['orders']:
        return JSONResponse({'code': 'ORDER_NOT_FOUND'}, 404)
    records = [event for event in state.get('spot_events', []) if event['orderId'] == oid]
    return {'orderId': oid, 'records': records, 'spent': amount(sum((Decimal(e['amount']) for e in records if e['kind'] == 'spent'), Decimal('0'))),
            'released': amount(sum((Decimal(e['amount']) for e in records if e['kind'] == 'released'), Decimal('0'))),
            'observation': 'local synthetic append-only events; not an independent production ledger'}


@router.post('/{sid}/spot/orders')
async def place(sid: str, body: dict, request: Request):
    state = session(request, sid)
    qty, price = number(body.get('quantity')), number(body.get('price'))
    if qty <= 0 or price <= 0:
        return JSONResponse({'code': 'INVALID_AMOUNT'}, 400)
    if qty % Decimal('0.01') or price % Decimal('0.01'):
        return JSONResponse({'code': 'PRECISION_ERROR'}, 400)
    frozen = qty * price
    if frozen > state['free']:
        return JSONResponse({'code': 'INSUFFICIENT_BALANCE'}, 400)
    oid = uuid4().hex
    state['orders'][oid] = {'quantity': qty, 'price': price, 'filled': Decimal('0'),
                            'locked': frozen, 'released': Decimal('0'), 'status': 'NEW'}
    state['free'] -= frozen
    state['locked'] += frozen
    spot_event(state, oid, 'frozen', frozen)
    return JSONResponse(order_view(oid, state['orders'][oid]), 201)


@router.api_route('/{sid}/spot/orders/{oid}', methods=['GET', 'DELETE'])
async def order(sid: str, oid: str, request: Request):
    state = session(request, sid)
    current = state['orders'].get(oid)
    if current is None:
        return JSONResponse({'code': 'ORDER_NOT_FOUND'}, 404)
    if request.method == 'DELETE':
        if current['status'] not in {'NEW', 'PARTIALLY_FILLED'}:
            return JSONResponse({'code': 'ORDER_NOT_CANCELABLE'}, 409)
        state['free'] += current['locked']
        state['locked'] -= current['locked']
        released = current['locked']
        current['released'] += released
        current.update(locked=Decimal('0'), status='CANCELED')
        spot_event(state, oid, 'released', released)
    return order_view(oid, current)


@router.post('/{sid}/spot/orders/{oid}/fills')
async def fill(sid: str, oid: str, body: dict, request: Request):
    state = session(request, sid)
    current = state['orders'].get(oid)
    if current is None:
        return JSONResponse({'code': 'ORDER_NOT_FOUND'}, 404)
    qty = number(body.get('quantity'))
    if current['status'] not in {'NEW', 'PARTIALLY_FILLED'} or qty <= 0 or qty + current['filled'] > current['quantity']:
        return JSONResponse({'code': 'INVALID_FILL'}, 400)
    current['filled'] += qty
    current['locked'] -= qty * current['price']
    state['locked'] -= qty * current['price']
    current['status'] = 'FILLED' if current['filled'] == current['quantity'] else 'PARTIALLY_FILLED'
    fill_id = spot_event(state, oid, 'spent', qty * current['price'])
    return {**order_view(oid, current), 'fillId': fill_id}


@router.get('/{sid}/spot/ledger/{oid}')
async def ledger(sid: str, oid: str, request: Request):
    state = session(request, sid)
    current = state['orders'].get(oid)
    if current is None:
        return JSONResponse({'code': 'ORDER_NOT_FOUND'}, 404)
    return {'orderId': oid, 'tradeQuantity': amount(current['filled']), 'spent': amount(current['filled'] * current['price']),
            'released': amount(current['released']), 'free': amount(state['free']), 'locked': amount(state['locked'])}


@router.api_route('/{sid}/futures/position', methods=['GET', 'POST'])
async def position(sid: str, request: Request):
    state = session(request, sid)
    if request.method == 'POST':
        body = await request.json()
        qty = number(body.get('quantity'))
        if body.get('reduceOnly') is not True or qty <= 0 or qty > state['position']:
            return JSONResponse({'code': 'REDUCE_ONLY_REJECTED'}, 400)
        state['position'] -= qty
    return {'side': 'LONG', 'quantity': amount(state['position'])}


@router.api_route('/{sid}/funds/transfers', methods=['GET', 'POST'])
async def transfer(sid: str, request: Request):
    state = session(request, sid)
    if request.method == 'GET':
        return {'wallet': amount(state['wallet']), 'futuresWallet': amount(state['futures_wallet']),
                'transferCount': len(state['transfers'])}
    body = await request.json()
    key, qty = body.get('clientId'), number(body.get('quantity'))
    if not isinstance(key, str) or not key.strip() or qty <= 0:
        return JSONResponse({'code': 'INVALID_TRANSFER'}, 400)
    if key in state['transfers']:
        if state['transfers'][key]['quantity'] != amount(qty):
            return JSONResponse({'code': 'IDEMPOTENCY_CONFLICT'}, 409)
        return state['transfers'][key]
    if qty > state['wallet']:
        return JSONResponse({'code': 'INSUFFICIENT_BALANCE'}, 400)
    state['wallet'] -= qty
    state['futures_wallet'] += qty
    state['transfers'][key] = {'transferId': uuid4().hex, 'clientId': key, 'quantity': amount(qty), 'status': 'SUCCESS'}
    return JSONResponse(state['transfers'][key], 201)


@router.get('/{sid}/dex/quote')
async def quote(sid: str, request: Request):
    session(request, sid)
    return {'chainId': 31337, 'quoteId': 'fixture-quote', 'minAmountOut': '900', 'amountOut': '950'}


@router.post('/{sid}/dex/swaps')
async def swap(sid: str, body: dict, request: Request):
    state = session(request, sid)
    if body.get('quoteId') != 'fixture-quote' or body.get('chainId') != 31337:
        return JSONResponse({'code': 'INVALID_QUOTE'}, 400)
    if number(body.get('minAmountOut')) > 950:
        return JSONResponse({'code': 'SLIPPAGE_EXCEEDED'}, 400)
    tx = '0x' + uuid4().hex + uuid4().hex
    state['receipts'][tx] = {'transactionHash': tx, 'status': '0x1', 'chainId': 31337, 'amountOut': '950',
                             'balanceDelta': '950', 'event': 'Swap'}
    return JSONResponse({'transactionHash': tx, 'accepted': True}, 201)


@router.get('/{sid}/dex/receipts/{tx}')
async def receipt(sid: str, tx: str, request: Request):
    state = session(request, sid)
    if tx not in state['receipts']:
        return JSONResponse({'code': 'TRANSACTION_NOT_FOUND'}, 404)
    return state['receipts'][tx]
