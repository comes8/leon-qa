"""Fixed native Go debugging; expected business errors do not destroy queryable state."""
import json
from .lab_model import LabDataset
from .settings import atomic_json

DEBUG_ACTIONS = {'transfer', 'query', 'verify'}


async def execute_debug(manager, op, env, dataset, folder, binary, base, pointer, opdir, runtime_env):
    from .lab_worker import snapshot_public
    fields = op['inputs']
    args = [binary, 'debug', '--base', base, '--file', pointer,
            '--observation-file', folder / '.runtime' / 'lab.json', '--action', op['action'],
            '--user', fields['test_user'], '--request-id', fields['business_request_id']]
    for name, flag in [('from_account', 'from'), ('to_account', 'to'), ('amount', 'amount'),
                       ('expected_funding', 'expected-funding'), ('expected_spot', 'expected-spot'),
                       ('expected_status', 'expected-status')]:
        if name in fields:
            args += ['--' + flag, fields[name]]
    raw = snapshot_public(json.loads(await manager.command(args, folder, runtime_env, timeout=35, log=opdir / 'debug.log')))
    if (raw.get('document_type') != 'leon.qa.debug' or raw.get('schema_version') != '1.0.0'
            or raw.get('dataset_id') != dataset['native_id'] or raw.get('action') != op['action']
            or raw.get('request_id') != fields['business_request_id'] or raw.get('user') != fields['test_user']
            or raw.get('verdict') not in {'PASS', 'FAIL', 'NOT_EVALUATED', 'UNKNOWN'}):
        raise ValueError('native debug receipt identity is invalid')
    assertions = raw.get('assertions')
    if not isinstance(assertions, list) or any(a.get('status') not in {'PASS', 'FAIL'} for a in assertions):
        raise ValueError('native assertion evidence invalid')
    if raw['verdict'] in {'PASS', 'FAIL'}:
        if op['action'] != 'verify' or not assertions or (raw['verdict'] == 'PASS') != all(a['status'] == 'PASS' for a in assertions):
            raise ValueError('native verdict contradicts assertions')
        required = {'balance', 'conservation', 'reconciliation', 'transfer_count', 'query_sql_agreement',
                    'transfer_status', 'transfer_amount', 'snapshot_sql_agreement'}
        if not required.issubset({a.get('rule_id') for a in assertions}):
            raise ValueError('mandatory debug assertion scope missing')
        for a in assertions:
            if a.get('operator') == 'eq':
                passed = json.dumps(a.get('expected'), sort_keys=True) == json.dumps(a.get('actual'), sort_keys=True)
            elif a.get('operator') == 'gte':
                values = [a.get('expected'), a.get('actual')]
                if any(isinstance(v, bool) or not isinstance(v, (int, str)) for v in values):
                    raise ValueError('invalid exact integer assertion')
                passed = int(values[1]) >= int(values[0])
            else:
                raise ValueError('unsupported native assertion operator')
            if passed != (a['status'] == 'PASS'):
                raise ValueError('native assertion contradicts expected/actual')
    if any(raw.get(k) and raw[k].get('dataset_id') != dataset['native_id'] for k in ['before', 'after']):
        raise ValueError('native snapshot is from another dataset')
    result = {**raw, 'operation_id': op['id'], 'platform_dataset_id': dataset['id'],
              'environment_id': env['id'], 'generation': dataset['generation'], 'source_sha256': env['source_sha256'],
              'associations': {k: fields[k] for k in ['requirement_ref', 'case_ref', 'review_note'] if k in fields}}
    atomic_json(opdir / 'result.json', result)
    await manager.store.patch(LabDataset, dataset['id'], {'status': 'ready',
        'snapshot': raw.get('after') or dataset['snapshot'], 'revision': dataset['revision'] + 1,
        'error_message': '结果未知，请先按原请求号查询，勿更换请求号重试' if raw['outcome'] == 'UNKNOWN' else None})
    return result
