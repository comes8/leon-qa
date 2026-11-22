from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from fastapi import HTTPException
from app.api.v1.Ntesterc_module.Ntesterc_web3 import interface_service as S,interface_schema as C
from tests.design_fixtures import CASES,POINTS
from tests.interface_fixtures import adapter_output
IDS={k:i+1 for i,k in enumerate(['session','balances','place','order','fill','cancel','events','cleanup'])}
class AdapterContractTests(unittest.IsolatedAsyncioTestCase):
 async def issues(self,output,env=None):
  p=SimpleNamespace(snapshot={'business':{'selected_cases':deepcopy(CASES['cases'])}});w=SimpleNamespace(service_id=3,environment_id=2,citations=[],analysis={})
  with patch.object(S.W,'catalogue',AsyncMock(return_value={i:None for i in IDS.values()})),patch.object(S.W.ApiAutomationService,'_load_env_vars',AsyncMock(return_value=env or {})),patch.object(S.W,'validate_plan',AsyncMock(return_value=[])):
   return await S.validate(None,p,None,w,output)
 async def test_complete_mapping_has_no_adapter_blocker(self):self.assertEqual(await self.issues(adapter_output(IDS,CASES['cases'])),[])
 async def test_renamed_case_is_blocked(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['case_id']='invented';self.assertTrue(any(i['case_id']=='*' for i in await self.issues(out)))
 async def test_missing_business_step_is_blocked(self):
  out=adapter_output(IDS,CASES['cases'])
  for s in out['scenarios'][0]['steps']:s['business_steps']=[];s['purpose']='setup'
  self.assertTrue(any('未完整映射' in i['message'] for i in await self.issues(out)))
 async def test_extra_business_step_is_blocked(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['steps'][3]['business_steps']=[999];self.assertTrue(any('不存在的业务步骤' in i['message'] for i in await self.issues(out)))
 async def test_response_amount_cannot_be_own_expected_value(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['steps'][-3]['validators'][1]['expect']='{{observed_free}}';self.assertTrue(any('独立十进制' in i['message'] for i in await self.issues(out)))
 async def test_unprepared_data_is_blocked(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['preparations'][0]['status']='needs_preparation';self.assertTrue(any('缺口' in i['message'] for i in await self.issues(out)))
 async def test_extraction_cannot_replace_environment(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['steps'][0]['extracts'][0]['name']='base_url';self.assertTrue(any('覆盖环境' in i['message'] for i in await self.issues(out,{'base_url':'http://127.0.0.1'})))
 async def test_coverage_and_rule_ids_cannot_expand(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['coverage_ids']=['invented'];out['scenarios'][0]['rule_ids']=['unknown'];self.assertTrue(any('无依据规则' in i['message'] for i in await self.issues(out)))
 def test_arbitrary_url_and_script_not_in_contract(self):
  out=adapter_output(IDS,CASES['cases']);out['scenarios'][0]['steps'][0]['url']='https://outside.invalid'
  with self.assertRaises(ValueError):C.InterfaceOutput.model_validate(out)
 async def test_local_scope_guards_origin_and_path(self):
  p=SimpleNamespace(snapshot={'target':{'scope':'local_mock'}});w=SimpleNamespace(environment_id=1,service_id=1)
  for url in ['https://api.binance.com/api','http://127.0.0.1:18171/api/v1/system/users','http://127.0.0.1:9999/api/v1/Ntesterc_web3/mock/sessions','http://127.0.0.1:18171/api/v1/Ntesterc_web3/mock/../system']:
   with self.subTest(url=url),patch.object(S.W,'catalogue',AsyncMock(return_value={1:SimpleNamespace(url=url,req={})})),patch.object(S.W.ApiAutomationService,'_load_env_vars',AsyncMock(return_value={})):
    with self.assertRaises(HTTPException):await S.target_guard(None,p,w)
class LocalObservationTests(unittest.TestCase):
 def test_events_and_cleanup_are_isolated(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from app.api.v1.Ntesterc_module.Ntesterc_web3.mock import router
  app=FastAPI();app.include_router(router);c=TestClient(app);sid=c.post('/sessions').json()['session_id'];base='/'+sid;other=c.post('/sessions').json()['session_id']
  self.assertEqual(c.get(base+'/spot/balances').json()['free'],'1000.00000000')
  oid=c.post(base+'/spot/orders',json={'quantity':'5','price':'10'}).json()['orderId'];path=base+'/spot/orders/'+oid
  self.assertIn('fillId',c.post(path+'/fills',json={'quantity':'2'}).json());order=c.delete(path).json();self.assertEqual((order['canceledQty'],order['activeRemainingQty']),('3.00000000','0.00000000'))
  before=c.get(base+'/spot/events/'+oid).json();self.assertEqual((before['spent'],before['released'],len(before['records'])),('20.00000000','30.00000000',3))
  self.assertEqual(c.delete(path).status_code,409);self.assertEqual(c.get(base+'/spot/events/'+oid).json(),before)
  self.assertTrue(c.delete(base+'/session').json()['deleted']);self.assertEqual(c.get(base+'/spot/balances').status_code,404);self.assertEqual(c.get('/'+other+'/spot/balances').json()['free'],'1000.00000000');c.delete('/'+other+'/session')
