"""Manual state-preparation boundaries; unit fixtures never count as live evidence."""
import asyncio
import json
import hashlib
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner import lab_controller as C
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_model import LabDataset, LabEnvironment
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_paths import LabPaths
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_schema import LabRequest
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_store import LabConflict, LabStore, public
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_worker import LabManager, snapshot_public
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.model import ensure_schema
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import Settings
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import atomic_json


class LabSchemaTests(unittest.TestCase):
    def test_mysql_process_identity_uses_double_precision(self):
        from sqlalchemy.dialects import mysql
        self.assertEqual(str(LabEnvironment.__table__.c.process_created.type.compile(dialect=mysql.dialect())), 'DOUBLE')
    def test_only_fixed_actions_and_exact_fields_are_allowed(self):
        base = {'project_id': 100, 'request_key': 'request_001', 'action': 'start'}
        for extra in [{'command': 'bash x'}, {'url': 'http://remote'}, {'env': {}}, {'funding': '100'},
                      {'environment_id': 'a' * 32}, {'action': 'transfer'}, {'project_id': True}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                LabRequest(**(base | extra))

    def test_seed_is_exact_nonnegative_bounded_decimal_text(self):
        base = {'project_id': 100, 'request_key': 'request_001', 'action': 'create',
                'environment_id': 'a' * 32, 'name': 'fixture', 'spot': '0'}
        for value in ['0', '10000000', '0.00000001', '12.34000000']:
            self.assertEqual(LabRequest(**base, funding=value).funding, value)
        for value in [-1, 1.2, True, '-1', '1e3', ' 1', '10000000.00000001', '0.000000001', '1;echo x']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                LabRequest(**base, funding=value)

    def test_rebuild_cannot_replace_immutable_seed(self):
        with self.assertRaises(ValueError):
            LabRequest(project_id=100, request_key='rebuild_001', action='rebuild', environment_id='a' * 32,
                       dataset_id='b' * 32, expected_revision=2, funding='999')

    def test_private_paths_reject_auto_run_ids_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            paths = LabPaths(Settings(tmp))
            with self.assertRaises(ValueError):
                paths.job_root('job_' + 'a' * 32)
            paths.root.symlink_to(outside)
            with self.assertRaises(ValueError):
                paths.job_root('env_' + 'a' * 32)

    def test_public_snapshots_preserve_integer_precision_without_credentials(self):
        result = snapshot_public({'accounts': [{'balance_minor': 900719925474099300000}], 'amount_minor': 0})
        self.assertEqual(result['accounts'][0]['balance_minor'], '900719925474099300000')
        self.assertEqual(result['amount_minor'], '0')
        self.assertNotIn('launch_token', public({'launch_token': 'private', 'registration': {'root': 'private'}}))


class LabStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.engine = create_async_engine('sqlite+aiosqlite:///' + str(self.root / 'lab.sqlite'))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        await ensure_schema(self.engine)
        self.store = LabStore(self.sessions)
        self.registration = {'root': '/local/registered', 'docker_endpoint': 'unix:///tmp/unit-lab.sock',
                             'tools': {k: sys.executable for k in ['bash', 'go', 'docker']}}

    async def asyncTearDown(self):
        await self.engine.dispose(); self.tmp.cleanup()

    async def start(self, key='start_001', project=100, user=10, ready=True):
        op, duplicate = await self.store.submit(LabRequest(project_id=project, action='start', request_key=key), user, self.registration)
        if ready:
            await self.store.patch(LabEnvironment, op['environment_id'], {'status': 'running'})
            await self.store.finish(op, {'status': 'running'})
        return op

    async def create(self, env, key='create_001', funding='1000', ready=True):
        body = LabRequest(project_id=100, action='create', request_key=key, environment_id=env,
                          name=key, funding=funding, spot='0')
        op, duplicate = await self.store.submit(body, 10, self.registration)
        if ready:
            await self.store.patch(LabDataset, op['dataset_id'], {'status': 'ready', 'revision': 2,
                'generation': 1, 'native_id': 'ds_' + op['dataset_id'], 'snapshot': {'dataset_id': 'ds_' + op['dataset_id'], 'accounts': []}})
            await self.store.finish(op, {'status': 'ready'})
        return op

    async def test_start_request_is_durable_and_idempotent(self):
        first = await self.start(ready=False)
        again, duplicate = await self.store.submit(LabRequest(project_id=100, action='start', request_key='start_001'), 10, self.registration)
        self.assertTrue(duplicate); self.assertEqual(first['id'], again['id'])
        self.assertEqual(len((await LabStore(self.sessions).listing(100, 10))['environments']), 1)

    async def test_one_owner_project_and_two_machine_slots(self):
        await self.start()
        with self.assertRaises(LabConflict):
            await self.start('other_001')
        await self.start('other_002', project=101)
        with self.assertRaises(LabConflict):
            await self.start('other_003', project=102)

    async def test_concurrent_start_does_not_allocate_duplicate_environment(self):
        results = await asyncio.gather(self.start('concurrent_001', ready=False), self.start('concurrent_002', ready=False), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertEqual(len((await self.store.listing(100, 10))['environments']), 1)

    async def test_create_retry_does_not_create_another_dataset(self):
        env = (await self.start())['environment_id']; first = await self.create(env, ready=False)
        duplicate, repeated = await self.store.submit(LabRequest(project_id=100, action='create', request_key='create_001',
            environment_id=env, name='create_001', funding='1000', spot='0'), 10, self.registration)
        self.assertTrue(repeated); self.assertEqual(first['dataset_id'], duplicate['dataset_id'])
        self.assertEqual(len((await self.store.listing(100, 10))['datasets']), 1)

    async def test_busy_environment_rejects_overlapping_mutation(self):
        env = (await self.start())['environment_id']; await self.create(env, ready=False)
        with self.assertRaises(LabConflict):
            await self.create(env, 'create_002')

    async def test_same_key_changed_payload_is_a_conflict(self):
        env = (await self.start())['environment_id']; await self.create(env)
        with self.assertRaises(LabConflict):
            await self.create(env, funding='20')

    async def test_stale_revision_and_cross_environment_ids_are_rejected(self):
        env = (await self.start())['environment_id']; ds = (await self.create(env))['dataset_id']
        for revision in [1, 99]:
            with self.assertRaises(LabConflict):
                await self.store.submit(LabRequest(project_id=100, action='delete', request_key=f'delete_{revision:03}',
                    environment_id=env, dataset_id=ds, expected_revision=revision), 10, self.registration)
        other = (await self.start('other_start', project=101))['environment_id']
        with self.assertRaises(LookupError):
            await self.store.submit(LabRequest(project_id=101, action='delete', request_key='foreign_001',
                environment_id=other, dataset_id=ds, expected_revision=2), 10, self.registration)

    async def test_stopping_environment_retires_only_its_datasets_and_keeps_snapshots(self):
        env = (await self.start())['environment_id']; ds = (await self.create(env))['dataset_id']
        snap = (await self.store.get(LabDataset, ds))['snapshot']
        await self.store.retire(env, 'stopped', True)
        row = await self.store.get(LabDataset, ds)
        self.assertEqual(row['status'], 'unavailable'); self.assertEqual(row['snapshot'], snap)
        self.assertIsNone((await self.store.get(LabEnvironment, env))['capacity_slot'])
        await self.start('start_again')

    async def test_rebuild_uses_its_explicit_pointer_and_archives_old_snapshot(self):
        env_id = (await self.start())['environment_id']; ds_id = (await self.create(env_id))['dataset_id']
        other_id = (await self.create(env_id, 'create_002', funding='20'))['dataset_id']
        op, _ = await self.store.submit(LabRequest(project_id=100, action='rebuild', request_key='rebuild_001',
            environment_id=env_id, dataset_id=ds_id, expected_revision=2), 10, self.registration)
        env = await self.store.get(LabEnvironment, env_id); manager = LabManager(Settings(self.root / 'runtime'), self.sessions, asyncio.Event())
        folder = manager.paths.job_root(env['session_id']); (folder / 'bin').mkdir(parents=True)
        (folder / 'bin/qa').write_bytes(b'unit-binary')
        atomic_json(folder / 'launch.json', {'binary_sha256': hashlib.sha256(b'unit-binary').hexdigest()})
        calls = []
        async def command(args, *a, **kw):
            calls.append([str(v) for v in args])
            return json.dumps({'dataset_id': 'ds_new', 'snapshot': {'dataset_id': 'ds_new', 'accounts': [{'balance_minor': 100000000000}]}}).encode()
        with patch.object(manager, 'base', return_value=('http://127.0.0.1:1234', 'local')), patch.object(manager, 'command', side_effect=command):
            await manager.data(op, env)
        row = await self.store.get(LabDataset, ds_id)
        self.assertEqual(row['native_id'], 'ds_new'); self.assertEqual(row['generation'], 2)
        self.assertEqual(len(row['history']), 1)
        self.assertEqual(row['snapshot']['accounts'][0]['balance_minor'], '100000000000')
        self.assertEqual((await self.store.get(LabDataset, other_id))['funding'], '20')
        self.assertTrue(all('--file' in c and 'current-dataset.json' not in ' '.join(c) for c in calls))
        self.assertTrue(all(ds_id in ' '.join(c) and other_id not in ' '.join(c) for c in calls))

    async def test_api_uses_native_actor_and_denies_other_users_operation(self):
        own = await self.start(); other = await self.start('other_user', project=101, user=11)
        app = FastAPI(); app.include_router(C.router)
        async def actor(): return 10
        async def db():
            async with self.sessions() as session: yield session
        app.dependency_overrides[C.actor] = actor; app.dependency_overrides[C.get_db] = db
        with patch.object(C, 'store', return_value=self.store), patch.object(C.ProjectService, '_check_project_member', new=AsyncMock()), \
             patch.object(C, 'Store') as native:
            native.return_value.health = AsyncMock(return_value={'status': 'idle'})
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
                data = (await client.get('/state', params={'project_id': 100})).json()['data']
                self.assertEqual(len(data['environments']), 1); self.assertNotIn('registration', data['environments'][0])
                self.assertEqual((await client.get('/operations/' + other['id'])).status_code, 404)
                self.assertEqual((await client.post('/operations', json={'project_id': 100, 'request_key': 'unsafe_001', 'action': 'start', 'command': 'x'})).status_code, 422)


if __name__ == '__main__':
    unittest.main()
