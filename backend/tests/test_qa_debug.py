import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_schema import LabRequest
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_store import LabStore, LabConflict
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_model import LabDataset, LabEnvironment
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker import LabManager
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.debug_worker import execute_debug
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.model import ensure_schema
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import Settings

BASE = dict(project_id=100, request_key='debug_0001', action='transfer', environment_id='a'*32,
            dataset_id='b'*32, expected_revision=2, test_user='alice', business_request_id='original-1',
            from_account='funding', to_account='spot', amount='100')

class DebugSchemaTests(unittest.TestCase):
    def test_only_fixed_profile_and_valid_direction(self):
        for extra in [{'url':'http://remote'}, {'command':'x'}, {'test_user':'admin'}, {'amount':'0'},
                      {'from_account':'spot'}, {'amount':100}, {'amount':'0.000000001'}, {'business_request_id':'../unsafe'}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError): LabRequest(**(BASE|extra))
        self.assertEqual(LabRequest(**BASE).amount,'100')

    def test_query_cannot_smuggle_mutating_parameters(self):
        query={k:v for k,v in BASE.items() if k not in ['from_account','to_account','amount']}
        query['action']='query'; self.assertEqual(LabRequest(**query).action,'query')
        with self.assertRaises(ValueError):LabRequest(**(query|{'amount':'100'}))

    def test_verification_requires_explicit_exact_expectations(self):
        with self.assertRaises(ValueError):LabRequest(**(BASE|{'action':'verify'}))
        b=BASE|dict(action='verify',expected_funding='20000000',expected_spot='0',expected_status='SUCCEEDED')
        self.assertEqual(LabRequest(**b).expected_funding,'20000000')
        with self.assertRaises(ValueError):LabRequest(**(b|{'expected_funding':'20000000.00000001'}))

    def test_associations_are_bounded_text_for_debug_only(self):
        self.assertEqual(LabRequest(**(BASE|{'review_note':'需求评审\n边界核对'})).review_note,'需求评审\n边界核对')
        with self.assertRaises(ValueError):LabRequest(project_id=100,request_key='start_001',action='start',case_ref='C1')
        with self.assertRaises(ValueError):LabRequest(**(BASE|{'review_note':'x'*1001}))

class DebugStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.engine=create_async_engine('sqlite+aiosqlite:///'+str(self.root/'unit.sqlite'))
        self.sessions=async_sessionmaker(self.engine,expire_on_commit=False);await ensure_schema(self.engine)
        self.store=LabStore(self.sessions)
        op,_=await self.store.submit(LabRequest(project_id=100,request_key='start_001',action='start'),10,{})
        self.env=op['environment_id'];await self.store.patch(LabEnvironment,self.env,{'status':'running'});await self.store.finish(op,{})
        op,_=await self.store.submit(LabRequest(project_id=100,request_key='create_001',action='create',environment_id=self.env,name='test',funding='1000',spot='0'),10,{})
        self.dataset=op['dataset_id'];await self.store.patch(LabDataset,self.dataset,{'status':'ready','revision':2,'generation':1,'native_id':'ds_test','snapshot':{'dataset_id':'ds_test'}});await self.store.finish(op,{})
        self.body=BASE|{'environment_id':self.env,'dataset_id':self.dataset,'requirement_ref':'REQ1','case_ref':'CASE1'}

    async def asyncTearDown(self):
        await self.engine.dispose();self.tmp.cleanup()

    async def test_debug_is_durable_busy_idempotent_and_preserves_links(self):
        op,dupe=await self.store.submit(LabRequest(**self.body),10,{})
        self.assertEqual(op['inputs']['case_ref'],'CASE1');self.assertFalse(dupe)
        again,dupe=await self.store.submit(LabRequest(**self.body),10,{})
        self.assertTrue(dupe);self.assertEqual(op['id'],again['id'])
        with self.assertRaises(LabConflict):await self.store.submit(LabRequest(**(self.body|{'request_key':'second_001'})),10,{})
        with self.assertRaises(LabConflict):await self.store.submit(LabRequest(**(self.body|{'amount':'101'})),10,{})

    async def test_unknown_cli_result_keeps_original_id_and_environment_queryable(self):
        op,_=await self.store.submit(LabRequest(**self.body),10,{})
        manager=LabManager(Settings(self.root/'runtime'),self.sessions,__import__('asyncio').Event())
        manager.data=AsyncMock(side_effect=RuntimeError('simulated lost native receipt'));manager.close=AsyncMock()
        with patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker.identity',return_value=True):await manager.execute(op)
        from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_model import LabOperation
        saved=await self.store.get(LabOperation,op['id']);data=await self.store.get(LabDataset,self.dataset)
        self.assertEqual(saved['result']['verdict'],'UNKNOWN');self.assertEqual(saved['result']['request_id'],'original-1')
        self.assertEqual(data['status'],'ready');manager.close.assert_not_awaited()

class DebugReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, raw, action='transfer'):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);manager=SimpleNamespace(command=AsyncMock(return_value=json.dumps(raw).encode()),store=SimpleNamespace(patch=AsyncMock()))
            op={'id':'op_test','action':action,'inputs':BASE|{'case_ref':'CASE1'}}
            env={'id':'env_test','source_sha256':'a'*64};dataset={'id':'data_test','native_id':'ds_test','generation':1,'revision':3,'snapshot':{'dataset_id':'ds_test'}}
            result=await execute_debug(manager,op,env,dataset,folder,folder/'qa','http://127.0.0.1:1',folder/'pointer',folder,{})
            return manager,result

    async def test_business_http_error_is_recorded_without_fabricating_pass(self):
        manager,r=await self.invoke({'document_type':'leon.qa.debug','schema_version':'1.0.0','dataset_id':'ds_test','action':'transfer','request_id':'original-1','user':'alice','verdict':'NOT_EVALUATED','outcome':'HTTP_ERROR','error_code':'IDEMPOTENCY_CONFLICT','assertions':[]})
        self.assertEqual(r['associations']['case_ref'],'CASE1');self.assertEqual(r['outcome'],'HTTP_ERROR');self.assertNotIn('registration',r)
        args=manager.command.call_args.args[0];self.assertIn('--request-id',args);self.assertIn('original-1',args)

    async def test_forged_pass_without_mandatory_evidence_is_rejected(self):
        with self.assertRaises(ValueError):await self.invoke({'document_type':'leon.qa.debug','schema_version':'1.0.0','dataset_id':'ds_test','action':'verify','request_id':'original-1','user':'alice','verdict':'PASS','outcome':'RESPONSE','assertions':[]},action='verify')
