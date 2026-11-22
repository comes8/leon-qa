from types import SimpleNamespace
from decimal import Decimal
import unittest
from app.api.v1.Ntesterc_module.Ntesterc_api.step_executor import _compare, _run_validators, VariableContext
from app.api.v1.Ntesterc_module.Ntesterc_project.knowledge_search import ranked_chunks
from app.api.v1.Ntesterc_module.Ntesterc_web3.schema import CreateWorkflow, ScenarioPlan
from app.api.v1.Ntesterc_module.Ntesterc_web3.service import redact


def test_decimal_assertions_preserve_large_financial_values():
    assert not _compare('9007199254740993.01', 'decimal_eq', '9007199254740993.02')
    assert _compare('2.00000000', 'decimal_eq', '2')
    assert _compare('950', 'decimal_gte', '900')
    assert not _compare('NaN', 'decimal_gte', '0')


def test_chinese_requirement_retrieves_source_rule():
    documents = [SimpleNamespace(id=1, title='现货部分成交与撤单', content='SPOT-LAB-01 部分成交后撤单，核对剩余冻结和独立流水解冻金额。'),
                 SimpleNamespace(id=2, title='合约资金费', content='资金费时间窗口核对')]
    hits = ranked_chunks(documents, '现货部分成交后撤单怎么核对解冻', 5)
    assert hits[0]['metadata']['document_id'] == 1
    assert 'SPOT-LAB-01' in hits[0]['content']
    assert ranked_chunks(documents, 'unrelated_zzzz', 5) == []


def test_evidence_masks_keys_nested_tokens_and_signed_urls():
    value = {'headers': {'Authorization': 'Bearer abc'}, 'api_secret': 'secret',
             'url': 'https://test.invalid/order?signature=abc&symbol=BTCUSDT',
             'body': {'quantity': '5', 'privateKey': 'wallet-secret'}}
    safe = redact(value)
    assert safe['headers']['Authorization'] == '[REDACTED]'
    assert 'signature=abc' not in safe['url']
    assert safe['body']['privateKey'] == '[REDACTED]'
    assert safe['body']['quantity'] == '5'


def test_undefined_financial_field_cannot_pass_decimal_equality():
    checks = [{'mode': 'jsonpath', 'check': '$.remainingFrozen', 'comparator': 'decimal_eq', 'expect': '0'}]
    results = _run_validators(checks, {'body': {}}, VariableContext())
    assert results[0]['result'] == 'fail'


def test_workflow_input_cannot_override_runner_with_shell():
    with unittest.TestCase().assertRaises(ValueError):
        CreateWorkflow(project_id=1, service_id=2, environment_id=1, writer_id=1, reviewer_id=2,
                       title='测试输入', requirement='本机现货部分成交后撤单业务回归', knowledge_base_ids=[4], command='echo bad')


class Web3WorkflowChecks(unittest.TestCase):
    test_decimal = staticmethod(test_decimal_assertions_preserve_large_financial_values)
    test_retrieval = staticmethod(test_chinese_requirement_retrieves_source_rule)
    test_redaction = staticmethod(test_evidence_masks_keys_nested_tokens_and_signed_urls)
    test_missing_money = staticmethod(test_undefined_financial_field_cannot_pass_decimal_equality)
    test_input_schema = staticmethod(test_workflow_input_cannot_override_runner_with_shell)


class TradingFixtureChecks(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.v1.Ntesterc_module.Ntesterc_web3.mock import router
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.session_id = self.client.post('/sessions').json()['session_id']
        self.root = '/' + self.session_id

    def test_spot_order_and_independent_ledger(self):
        created = self.client.post(self.root + '/spot/orders', json={'quantity':'5','price':'10'})
        self.assertEqual(created.status_code, 201)
        order = self.root + '/spot/orders/' + created.json()['orderId']
        partial = self.client.post(order + '/fills', json={'quantity':'2'}).json()
        self.assertEqual(Decimal(partial['remainingFrozen']), Decimal('30'))
        self.assertEqual(self.client.delete(order).json()['status'], 'CANCELED')
        ledger = self.client.get(self.root + '/spot/ledger/' + created.json()['orderId']).json()
        self.assertEqual((Decimal(ledger['spent']), Decimal(ledger['released']), Decimal(ledger['free'])),
                         (Decimal('20'), Decimal('30'), Decimal('980')))
        self.assertEqual(self.client.delete(order).status_code, 409)

    def test_futures_reduction_rejects_excess_and_isolates_sessions(self):
        changed = self.client.post(self.root + '/futures/position', json={'quantity':'2','reduceOnly':True})
        self.assertEqual(Decimal(changed.json()['quantity']), Decimal('3'))
        self.assertEqual(self.client.post(self.root + '/futures/position', json={'quantity':'4','reduceOnly':True}).status_code, 400)
        fresh = self.client.post('/sessions').json()['session_id']
        self.assertEqual(Decimal(self.client.get('/' + fresh + '/futures/position').json()['quantity']), Decimal('5'))

    def test_transfer_idempotency_and_payload_conflict(self):
        url = self.root + '/funds/transfers'
        first = self.client.post(url, json={'clientId':'same-id','quantity':'10'})
        second = self.client.post(url, json={'clientId':'same-id','quantity':'10'})
        self.assertEqual((first.status_code,second.status_code), (201,200))
        self.assertEqual(first.json()['transferId'], second.json()['transferId'])
        self.assertEqual(self.client.post(url,json={'clientId':'same-id','quantity':'20'}).status_code,409)
        balances = self.client.get(url).json()
        self.assertEqual(balances['transferCount'],1)
        self.assertEqual(Decimal(balances['wallet']),Decimal('90'))

    def test_dex_quote_receipt_and_slippage_failure(self):
        quote = self.client.get(self.root + '/dex/quote').json()
        body = {'quoteId':quote['quoteId'],'chainId':quote['chainId'],'minAmountOut':'900'}
        accepted = self.client.post(self.root + '/dex/swaps',json=body)
        self.assertEqual(accepted.status_code,201)
        receipt = self.client.get(self.root + '/dex/receipts/' + accepted.json()['transactionHash']).json()
        self.assertEqual(receipt['status'],'0x1')
        self.assertGreaterEqual(Decimal(receipt['balanceDelta']),Decimal('900'))
        self.assertEqual(self.client.post(self.root + '/dex/swaps',json={**body,'minAmountOut':'951'}).status_code,400)


class BinanceSigningChecks(unittest.TestCase):
    def test_signature_is_built_from_exact_query(self):
        import hashlib, hmac
        from urllib.parse import urlencode
        from app.api.v1.Ntesterc_module.Ntesterc_web3.binance_auth import sign_request
        params={'symbol':'BTCUSDT','side':'BUY','timestamp':12345,'recvWindow':5000}
        headers,signed,_=sign_request({'auth_api_key':'dummy-key','auth_api_secret':'dummy-secret'},{},params)
        self.assertEqual(headers['X-MBX-APIKEY'],'dummy-key')
        self.assertEqual(signed['signature'],hmac.new(b'dummy-secret',urlencode(params).encode(),hashlib.sha256).hexdigest())
        self.assertNotIn('signature',params)

    def test_missing_secret_reference_is_rejected(self):
        from app.api.v1.Ntesterc_module.Ntesterc_web3.binance_auth import sign_request
        with self.assertRaises(ValueError):
            sign_request({'auth_api_key':'{{api_key}}','auth_api_secret':'{{api_secret}}'},{},{})


class WorkflowContractChecks(unittest.TestCase):
    def test_strict_field_absence_differs_from_null(self):
        checks=[{'mode':'jmespath','check':"contains(keys(body), 'transactionHash')",'comparator':'eq','expect':False}]
        self.assertEqual(_run_validators(checks,{'body':{}},VariableContext())[0]['result'],'pass')
        self.assertEqual(_run_validators(checks,{'body':{'transactionHash':None}},VariableContext())[0]['result'],'fail')

    def test_extracted_json_values_preserve_types(self):
        variables = VariableContext({'chain_id': 31337, 'enabled': False})
        variables.set('payload', {'amount':'900'})
        self.assertEqual(variables.resolve({'chainId':'{{chain_id}}', 'reduceOnly':'${enabled}'}),
                         {'chainId':31337,'reduceOnly':False})
        self.assertEqual(variables.resolve('{{payload}}'), {'amount':'900'})
        self.assertEqual(variables.resolve('chain-{{chain_id}}'), 'chain-31337')

    def test_missing_jmespath_extract_fails(self):
        result = VariableContext().apply_extracts([{'name':'order_id','path':'body.orderId'}], {'body':{}})
        self.assertEqual(result[0]['extract_result'], 'fail')

    def test_registered_path_override_cannot_replace_host(self):
        from app.api.v1.Ntesterc_module.Ntesterc_web3.service import step_url
        url='{{base_url}}/{{session_id}}/orders/{{order_id}}'
        self.assertEqual(step_url(url, {'order_id':'missing-{{run_id}}'}),
                         '{{base_url}}/{{session_id}}/orders/missing-{{run_id}}')
        with self.assertRaises(ValueError):
            step_url(url, {'base_url':'https://other.invalid'})
        self.assertEqual(step_url('https://qa.invalid/orders/{{order_id}}', {'order_id':'a/b?c'}),
                         'https://qa.invalid/orders/a%2Fb%3Fc')

    def test_key_value_records_and_raw_json_are_redacted(self):
        self.assertEqual(redact({'key':'X-MBX-APIKEY','value':'demo-secret'})['value'], '[REDACTED]')
        self.assertNotIn('demo-secret', redact('{"api_secret":"demo-secret","quantity":"5"}'))

    def test_rule_resolution_never_creates_a_missing_rule(self):
        from app.api.v1.Ntesterc_module.Ntesterc_web3.service import resolve_rule_sources
        item=SimpleNamespace(case_id='case-1',rule_ids=['SIM-SESSION-01','MISSING-01'],source_ids=[12])
        changes=resolve_rule_sources([item],[{'source_id':11,'content':'SIM-SESSION-01 session rules'},
                                          {'source_id':12,'content':'SIM-FUNDS-01 funding rules'}])
        self.assertEqual(item.source_ids,[12,11])
        self.assertEqual([change['rule'] for change in changes],['SIM-SESSION-01'])

    def test_wrong_source_numbers_are_resolved_only_when_rules_are_unambiguous(self):
        from app.api.v1.Ntesterc_module.Ntesterc_web3.service import resolve_rule_sources
        good=SimpleNamespace(id='C1',rule_ids=['RULE-1'],source_ids=[999])
        unknown=SimpleNamespace(id='C2',rule_ids=['NO-RULE'],source_ids=[999])
        resolve_rule_sources([good,unknown],[{'source_id':11,'content':'RULE-1 confirmed'}])
        self.assertEqual(good.source_ids,[11])
        self.assertEqual(unknown.source_ids,[999])


class TechnicalGateChecks(unittest.IsolatedAsyncioTestCase):
    async def test_loopback_requests_ignore_broken_machine_proxy(self):
        from unittest.mock import patch
        from datetime import timedelta
        import requests
        from app.api.v1.Ntesterc_module.Ntesterc_api.service import ApiAutomationService
        response=requests.Response()
        response.status_code=201
        response._content=b'{"session_id":"local"}'
        response.elapsed=timedelta(milliseconds=2)
        response.request=requests.Request('POST','http://127.0.0.1:18171/sessions',json={}).prepare()
        with patch('requests.post',return_value=response) as send:
            result=await ApiAutomationService._send_request(2,'http://127.0.0.1:18171/sessions',{}, {},2,{}, {},{},[],{})
            self.assertEqual(result['code'],201)
            self.assertEqual(send.call_args.kwargs['proxies'],{'http':'','https':'','all':''})
            await ApiAutomationService._send_request(2,'https://qa.example.invalid/sessions',{}, {},2,{}, {},{},[],{})
            self.assertNotIn('proxies',send.call_args.kwargs)

    async def test_invalid_source_and_undefined_variable_are_blocked(self):
        from unittest.mock import AsyncMock, patch
        from app.api.v1.Ntesterc_module.Ntesterc_web3 import service
        row=SimpleNamespace(service_id=2,environment_id=1,
            citations=[{'source_id':1,'content':'RULE-10 is not RULE-1'}],
            analysis={'coverage':[{'id':'C1','needs_confirmation':False}]},
            draft={'scenarios':[{'case_id':'case-1','name':'未知订单', 'category':'negative','priority':'P1',
                'coverage_ids':['C1'],'source_ids':[1],'rule_ids':['RULE-9'],'preconditions':[], 'expected':'404',
                'steps':[{'name':'查询','api_id':1,'validators':[
                    {'mode':'jmespath','check':'status_code','expect':404},
                    {'mode':'jsonpath','check':'$.code','expect':'ORDER_NOT_FOUND'}]}]}]})
        api=SimpleNamespace(url='http://127.0.0.1/orders/{{order_id}}',req={'method':1})
        with patch.object(service,'catalogue',AsyncMock(return_value={1:api})), \
             patch.object(service.ApiAutomationService,'_load_env_vars',AsyncMock(return_value={})):
            issues=await service.validate_plan(None,row)
            self.assertIn('规则编号缺少来源',issues[0]['message'])
            self.assertIn('未定义变量 order_id',issues[0]['message'])
            row.draft['scenarios'][0]['rule_ids']=['RULE-1']
            row.citations[0]['content']='RULE-10'
            issues=await service.validate_plan(None,row)
            self.assertIn('规则编号缺少来源',issues[0]['message'])

    async def test_concurrent_status_change_rejects_stale_approval(self):
        from unittest.mock import AsyncMock
        from fastapi import HTTPException
        from app.api.v1.Ntesterc_module.Ntesterc_web3.service import claim
        db=SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(rowcount=0)),commit=AsyncMock())
        row=SimpleNamespace(id=1,revision=4,status='review_ready')
        with self.assertRaises(HTTPException) as error:
            await claim(db,row,{'review_ready'},'publishing',4)
        self.assertEqual(error.exception.status_code,409)
        db.commit.assert_not_awaited()

    async def test_edited_published_cases_require_review(self):
        from unittest.mock import AsyncMock, patch
        from fastapi import HTTPException
        from app.api.v1.Ntesterc_module.Ntesterc_web3 import service
        row=SimpleNamespace(scope='local_mock',environment_id=1,publication={'suite_id':2,'cases':[
            {'native_case_id':1,'script_sha256':service.fingerprint([{'name':'reviewed'}])}]})
        case=SimpleNamespace(enabled_flag=1,suite_id=2,script=[{'name':'changed'}])
        db=SimpleNamespace(get=AsyncMock(return_value=case))
        with patch.object(service.ApiAutomationService,'_load_env_vars',AsyncMock(return_value={})):
            with self.assertRaises(HTTPException) as error:
                await service.verify_targets(db,row)
            self.assertEqual(error.exception.status_code,409)

    async def test_failed_step_blocks_dependents_but_next_case_is_independent(self):
        from unittest.mock import AsyncMock, Mock, patch
        from app.api.v1.Ntesterc_module.Ntesterc_web3 import service
        from app.api.v1.Ntesterc_module.Ntesterc_api.step_executor import StepResult
        first=SimpleNamespace(id=1,name='first',enabled_flag=1,script=[{'name':'失败步骤'},{'name':'关联二'},{'name':'关联三'}])
        second=SimpleNamespace(id=2,name='second',enabled_flag=1,script=[{'name':'独立用例'}])
        row=SimpleNamespace(scope='local_mock',environment_id=1,created_by=1,id=99,title='失败证据检查',service_id=2,
            executions=[],publication={'cases':[{'case_id':'C1','native_case_id':1,'name':'first'},
                                               {'case_id':'C2','native_case_id':2,'name':'second'}]})
        db=SimpleNamespace(get=AsyncMock(side_effect=[first,second]),add=Mock(),flush=AsyncMock(),commit=AsyncMock())
        contexts=[]
        class FakeExecutor:
            def __init__(self,*args): contexts.append(args[5])
            async def execute(self,step):
                return StepResult(name=step['name'],step_type='api',success=step['name']!='失败步骤',
                                  response={'code':200,'body':{'quantity':'wrong'}})
        with patch.object(service,'verify_targets',AsyncMock()), \
             patch.object(service.ApiAutomationService,'_load_env_vars',AsyncMock(return_value={})), \
             patch.object(service,'StepExecutor',FakeExecutor):
            await service.execute_plan(db,row)
        receipt=row.executions[-1]
        self.assertEqual((receipt['total_steps'],receipt['passed_steps'],receipt['failed_steps'],receipt['blocked_steps']),(4,1,1,2))
        self.assertEqual([case['status'] for case in receipt['cases']],['failed','passed'])
        self.assertEqual(row.status,'failed')
        self.assertIsNot(contexts[0],contexts[1])
