import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import FastAPI, HTTPException
import httpx
from scripts import local_stack as L
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker import LabManager
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.model import RunnerJob, RunnerWorker
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import Settings
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner import controller as C


class StackIdentityTests(unittest.TestCase):
    def fake(self, **changes):
        p=Mock();p.pid=10;p.is_running.return_value=True;p.status.return_value='running';p.cwd.return_value='/local'
        p.cmdline.return_value=['node','/local/vite.js'];p.exe.return_value='/usr/bin/node';p.create_time.return_value=123.125
        for k,v in changes.items():getattr(p,k).return_value=v
        return p

    def test_exact_executable_arguments_directory_and_creation_time(self):
        record={'pid':10,'process_created':123.125};spec=(Path('/local'),['/usr/bin/node','/local/vite.js'],18170,'/')
        for changes,expected in [({},True),({'create_time':124},False),({'cwd':'/other'},False),({'cmdline':['node','/other.js']},False),({'exe':'/usr/bin/python'},False)]:
            with self.subTest(changes=changes),patch.object(L,'specification',return_value=spec),patch.object(L.psutil,'Process',return_value=self.fake(**changes)):
                self.assertEqual(L.identity('frontend',record),expected)

    def test_missing_precise_identity_is_only_allowed_for_verified_legacy_adoption(self):
        with patch.object(L,'specification',return_value=(Path('/local'),['/usr/bin/node','/local/vite.js'],18170,'/')),patch.object(L.psutil,'Process',return_value=self.fake()):
            self.assertFalse(L.identity('frontend',{'pid':10}));self.assertTrue(L.identity('frontend',{'pid':10},legacy=True))

    def test_stop_never_signals_unverified_pid(self):
        with patch.object(L,'load_record',return_value={'pid':999,'process_created':1}),patch.object(L,'identity',return_value=False),patch.object(L.os,'killpg') as kill:
            self.assertTrue(L.stop_service('backend')['stopped']);kill.assert_not_called()

    def test_port_conflict_does_not_start_or_kill_anything(self):
        with patch.object(L,'load_record',return_value={}),patch.object(L,'identity',return_value=False),patch.object(L,'occupied',return_value=True),patch.object(L.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'非所属进程'):L.start_service('backend')
            spawn.assert_not_called()

    def test_symlink_process_record_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'target').write_text('{}');(p/'backend-process.json').symlink_to(p/'target')
            with patch.object(L,'RUNTIME',p),self.assertRaises(RuntimeError):L.load_record('backend')

    def test_runner_identity_columns_are_double(self):
        from sqlalchemy.dialects import mysql
        for model in [RunnerJob,RunnerWorker]:self.assertEqual(str(model.__table__.c.process_created.type.compile(dialect=mysql.dialect())),'DOUBLE')

    def test_already_running_worker_is_not_declared_ready_when_blocked(self):
        receipt=SimpleNamespace(returncode=0,stdout='{"already_running":true,"pid":10}\n')
        with patch.object(L.subprocess,'run',return_value=receipt),patch('app.core.database.engine',SimpleNamespace(dispose=AsyncMock())),patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.store.Store') as store:
            store.return_value.health=AsyncMock(return_value={'status':'blocked'})
            with self.assertRaisesRegex(RuntimeError,'阻塞'):L.worker('start')

    def test_diagnostic_heartbeat_also_requires_live_precise_process_identity(self):
        from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.health import verified_worker
        with tempfile.TemporaryDirectory() as t:
            settings=Settings(t);(Path(t)/'worker-process.json').write_text(json.dumps({'pid':10,'process_created':123.125}))
            p=self.fake();p.cmdline.return_value=['python','-m','app.api.v1.Ntesterc_module.Ntesterc_qa_runner.worker','--runtime',str(settings.runtime)]
            with patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.health.psutil.Process',return_value=p):
                self.assertTrue(verified_worker({'pid':10},settings));p.status.return_value='stopped';self.assertFalse(verified_worker({'pid':10},settings));p.status.return_value='running';p.create_time.return_value=124;self.assertFalse(verified_worker({'pid':10},settings))


class ManualHealthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.manager=LabManager(Settings(Path(self.tmp.name)),None,asyncio.Event())
        self.env={'id':'a'*32,'session_id':'env_'+'a'*32,'status':'running','process_pid':123,'process_created':12.25,'launch_token':'b'*32}
        self.folder=self.manager.paths.job_root(self.env['session_id']);self.folder.mkdir(parents=True)
        self.manager.store=SimpleNamespace(environments=AsyncMock(return_value=[self.env]),recover_operations=AsyncMock())
        self.manager.base=Mock(return_value=('http://127.0.0.1:1','c'*64));self.manager.close=AsyncMock()
        self.client=AsyncMock();self.client.__aenter__.return_value=self.client

    async def asyncTearDown(self):self.tmp.cleanup()

    async def probe(self, healthy):
        self.manager.next_health_check=0
        self.client.get.return_value=SimpleNamespace(status_code=200 if healthy else 503,json=lambda:{'profile':'local-synthetic-v1'})
        with patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker.identity',return_value=True),patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker.httpx.AsyncClient',return_value=self.client):await self.manager.monitor()

    async def test_transient_failure_resets_without_destroying_environment(self):
        await self.probe(False);await self.probe(True);self.manager.close.assert_not_awaited()
        self.assertEqual(json.loads((self.folder/'health.json').read_text())['consecutive_failures'],0)

    async def test_three_failures_trigger_owned_cleanup_and_keep_clear_reason(self):
        for _ in range(3):await self.probe(False)
        self.manager.close.assert_awaited_once();self.assertEqual(self.manager.close.call_args.args[1],'interrupted')

    async def test_probe_has_a_rate_limit(self):
        await self.probe(True)
        with patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker.httpx.AsyncClient',return_value=self.client):await self.manager.monitor()
        self.assertEqual(self.client.get.await_count,1)

    async def test_lost_supervisor_does_not_request_unrelated_endpoint(self):
        with patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker.identity',return_value=False),patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker.httpx.AsyncClient',return_value=self.client):await self.manager.monitor()
        self.manager.close.assert_awaited_once();self.client.get.assert_not_awaited()

    async def test_readiness_waits_for_recovery(self):
        entered=asyncio.Event();release=asyncio.Event()
        async def close(*a):entered.set();await release.wait()
        self.manager.close=AsyncMock(side_effect=close);self.manager.stopping.set()
        task=asyncio.create_task(self.manager.run());await entered.wait();self.assertFalse(self.manager.ready.is_set());release.set();await task;self.assertTrue(self.manager.ready.is_set())

    async def test_cleanup_failure_still_attempts_other_owned_environments(self):
        self.manager.store.environments.return_value=[];self.manager.owned={'one':{'id':'one'},'two':{'id':'two'}};self.manager.stopping.set()
        self.manager.close.side_effect=[RuntimeError('injected'),{}]
        with self.assertRaises(RuntimeError):await self.manager.run()
        self.assertEqual(self.manager.close.await_count,2)


class DiagnosticsAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostics_requires_project_membership_and_is_read_only(self):
        app=FastAPI();app.include_router(C.router)
        async def actor():return 10
        async def db():yield None
        app.dependency_overrides[C.actor]=actor;app.dependency_overrides[C.get_db]=db
        with patch.object(C.ProjectService,'_check_project_member',new=AsyncMock(side_effect=HTTPException(403,'not member'))),patch('app.api.v1.Ntesterc_module.Ntesterc_qa_runner.health.for_project',new=AsyncMock()) as collect:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as client:
                self.assertEqual((await client.get('/diagnostics',params={'project_id':100})).status_code,403)
                self.assertEqual((await client.post('/diagnostics',json={'action':'stop'})).status_code,405)
            collect.assert_not_awaited()
