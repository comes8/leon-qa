"""Phase-two tests: no LLM, no real exchange endpoints, isolated task database."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.Ntesterc_module.Ntesterc_qa_runner import controller as C
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.model import ensure_schema
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.protocol import ProtocolError, artifact_path, import_report, validate_case
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.schema import CreateJob
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import Settings, atomic_json
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.store import RequestConflict, Store
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner import processes
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner import worker as W


class RunnerStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.settings = Settings(self.root / 'runtime')
        kit = self.root / 'kit'
        kit.mkdir()
        (kit / 'go.mod').write_text('module github.com/comes8/leon-qa-kit\n')
        (kit / 'qa.sh').write_text('not executed by these tests')
        self.registration = {'version': 1, 'project_key': 'leon-qa-kit', 'root': str(kit), 'docker_endpoint': 'unix:///tmp/unit-docker.sock',
                             'tools': {name: sys.executable for name in ['bash', 'go', 'docker']}}
        atomic_json(self.settings.config_file, self.registration)
        catalog = json.loads((Path(C.__file__).parent / 'data/suite-v1.json').read_text())
        atomic_json(self.settings.catalog_file, {'registered_root': str(kit), 'catalog': catalog})
        self.engine = create_async_engine('sqlite+aiosqlite:///' + str(self.root / 'jobs.sqlite'))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        await ensure_schema(self.engine)
        self.store = Store(self.sessions)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.tmp.cleanup()

    async def submit(self, key='request_0001', user=10, **changes):
        body = CreateJob(project_id=100, request_key=key, **changes)
        return await self.store.submit(body, user, self.registration, self.settings)

    async def test_request_is_durable_and_idempotent(self):
        first, duplicate = await self.submit()
        self.assertFalse(duplicate)
        again, duplicate = await self.submit()
        self.assertTrue(duplicate)
        self.assertEqual(first['id'], again['id'])
        reopened = Store(self.sessions)
        self.assertEqual((await reopened.get(first['id']))['status'], 'queued')

    async def test_changed_payload_cannot_reuse_key(self):
        await self.submit()
        with self.assertRaises(RequestConflict):
            await self.submit(run_kind='selftest')

    async def test_same_key_is_scoped_to_user(self):
        first, _ = await self.submit(user=10)
        second, _ = await self.submit(user=11)
        self.assertNotEqual(first['id'], second['id'])

    async def test_only_one_claim_wins(self):
        job, _ = await self.submit()
        results = await asyncio.gather(self.store.claim('worker-a'), self.store.claim('worker-b'))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual((await self.store.get(job['id']))['status'], 'running')

    async def test_queue_cancel_does_not_launch_and_is_idempotent(self):
        job, _ = await self.submit()
        cancelled = await self.store.cancel(job['id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertIsNone(await self.store.claim('worker'))
        revision = cancelled['revision']
        self.assertEqual((await self.store.cancel(job['id']))['revision'], revision)
        self.assertFalse(self.settings.job_root(job['run_id']).exists())

    async def test_running_cancel_is_a_request_not_success(self):
        job, _ = await self.submit()
        await self.store.claim('worker')
        result = await self.store.cancel(job['id'])
        self.assertEqual(result['status'], 'cancelling')
        self.assertIsNone(result['result_status'])
        self.assertIsNone(await self.store.change(job['id'], {'running'}, {'status': 'completed'}, 'bad', 'bad'))

    async def test_events_have_unique_ordered_revision(self):
        job, _ = await self.submit()
        await self.store.claim('worker')
        await self.store.cancel(job['id'])
        events = await self.store.events(job['id'])
        self.assertEqual([e['seq'] for e in events], [1, 2, 3])
        self.assertEqual([e['code'] for e in events], ['queued', 'started', 'cancel_requested'])

    async def test_api_authorization_boundaries_and_rejected_shell_input(self):
        app = FastAPI()
        app.include_router(C.router)

        async def actor():
            return 10

        async def db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[C.actor] = actor
        app.dependency_overrides[C.get_db] = db
        with patch.object(C, 'store', return_value=self.store), patch.object(C, 'Settings', return_value=self.settings), \
             patch.object(C.ProjectService, '_check_project_member', new=AsyncMock()):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
                body = {'project_id': 100, 'request_key': 'api_request_001'}
                response = await client.post('/jobs', json=body)
                self.assertEqual(response.status_code, 202, response.text)
                job = response.json()['data']['job']
                self.assertNotIn('launch_token', job)
                again = await client.post('/jobs', json=body)
                self.assertEqual(again.status_code, 200)
                self.assertEqual(again.json()['data']['job']['id'], job['id'])
                denied = await client.post('/jobs', json={**body, 'command': 'echo unsafe'})
                self.assertEqual(denied.status_code, 422)
                denied = await client.post('/jobs', json={**body, 'env': {'DOCKER_HOST': 'remote'}})
                self.assertEqual(denied.status_code, 422)
                self.assertEqual((await client.get('/jobs/' + 'f' * 32)).status_code, 404)
                other, _ = await self.submit(key='other_user_request', user=11)
                self.assertEqual((await client.get('/jobs/' + other['id'])).status_code, 404)
                self.assertEqual((await client.post('/jobs/' + other['id'] + '/cancel')).status_code, 404)
                cancelled = await client.post('/jobs/' + job['id'] + '/cancel')
                self.assertEqual(cancelled.json()['data']['status'], 'cancelled')

    async def test_missing_and_invalid_auth_are_rejected(self):
        app = FastAPI()
        app.include_router(C.router)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local') as client:
            self.assertEqual((await client.get('/catalog')).status_code, 401)
            self.assertEqual((await client.get('/catalog', headers={'Authorization': 'Bearer not-a-token'})).status_code, 401)

    async def test_dead_supervisor_requires_group_verification(self):
        submitted, _ = await self.submit()
        job = await self.store.claim('worker')
        worker = W.Worker(self.settings, self.sessions, self.engine)
        worker.registration = self.registration
        worker.catalog = self.settings.catalog()
        fake_process = SimpleNamespace(pid=999999, returncode=1)
        with patch.object(W.asyncio, 'create_subprocess_exec', new=AsyncMock(return_value=fake_process)), \
             patch.object(W, 'cleanup', new=AsyncMock(return_value={'errors': []})) as cleanup:
            await worker.execute(job)
            self.assertTrue(cleanup.await_args.kwargs['stop'])
        row = await self.store.get(submitted['id'])
        self.assertEqual(row['result_status'], 'ENV_ERROR')
        self.assertIsNone(row['result'])

    async def test_database_loss_still_attempts_owned_cleanup(self):
        worker = W.Worker(self.settings, self.sessions, self.engine)
        worker.registration = self.registration
        job, _ = await self.submit()
        job.update(process_pid=999999, process_created=1)
        worker.store.get = AsyncMock(side_effect=OSError('test DB unavailable'))
        worker.store.change = AsyncMock(side_effect=OSError('test DB unavailable'))
        with patch.object(W, 'find_supervisor', return_value=None), \
             patch.object(W, 'cleanup', new=AsyncMock(return_value={'errors': []})) as cleanup:
            with self.assertRaises(OSError):
                await worker.end_stopped(job, 'interrupted', 'test DB outage')
            cleanup.assert_awaited_once()
            self.assertTrue(cleanup.await_args.kwargs['stop'])

    async def test_container_cleanup_continues_if_group_identity_is_unverifiable(self):
        job, _ = await self.submit()
        job['process_pid'] = 999999
        with patch.object(processes, 'stop_group', new=AsyncMock(side_effect=RuntimeError('identity mismatch'))), \
             patch.object(processes, 'docker_cleanup', return_value={'remaining': 0}) as docker:
            result = await processes.cleanup(job, self.settings, self.registration, stop=True)
        docker.assert_called_once()
        self.assertEqual(result['remaining'], 0)
        self.assertEqual(len(result['errors']), 1)


class RunnerProtocolTests(unittest.TestCase):
    def test_child_and_cleanup_cannot_follow_changed_docker_context(self):
        registration = {'tools': {key: sys.executable for key in ['bash', 'go', 'docker']},
                        'docker_endpoint': 'unix:///tmp/pinned-local.sock'}
        with patch.dict(processes.os.environ, {'DOCKER_CONTEXT': 'remote-context', 'DOCKER_HOST': 'ssh://remote'}):
            env = processes.child_environment(registration, 'token')
        self.assertEqual(env['DOCKER_HOST'], registration['docker_endpoint'])
        self.assertNotIn('DOCKER_CONTEXT', env)
        registration['docker_endpoint'] = 'ssh://remote'
        with self.assertRaises(ValueError):
            processes.child_environment(registration, 'token')

    def test_unknown_parameters_and_suite_are_rejected(self):
        for extra in [{'command': 'echo x'}, {'output_dir': '/tmp/x'}, {'run_id': 'other'},
                      {'suite_id': 'other'}, {'run_kind': 'manual'}, {'timeout_seconds': 0}, {'timeout_seconds': True}]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                CreateJob(project_id=1, request_key='request_001', **extra)

    def test_artifact_paths_cannot_escape_or_follow_links(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            path = Path(root).resolve()
            (path / 'valid.json').write_text('{}')
            (path / 'link').symlink_to(outside, target_is_directory=True)
            for name in ['../outside', '/absolute', 'a/../valid.json', 'link/file', 'x\\y']:
                with self.subTest(name=name), self.assertRaises((ValueError, FileNotFoundError)):
                    artifact_path(path, name)
            self.assertEqual(artifact_path(path, 'valid.json'), path / 'valid.json')

    def test_non_owned_process_is_never_signalled(self):
        job = {'process_pid': 12345, 'launch_token': 'different', 'process_created': 1}
        with patch.object(processes, 'identity', return_value=False), \
             patch.object(processes.os, 'killpg') as kill:
            with self.assertRaises(RuntimeError):
                asyncio.run(processes.stop_group(job))
            kill.assert_called_once_with(12345, 0)

    @staticmethod
    def case_fixture():
        snapshot = {'dataset_id': 'fixture', 'accounts': [], 'transfers': [], 'ledger': []}
        return {'schema_version': '1.0.0', 'document_type': 'leon.qa.case',
                'project_id': 'leon-qa-kit', 'suite_id': 'funds-transfer-v1', 'suite_version': '1.0.0',
                'run_id': 'fixture_001', 'run_kind': 'regression', 'case_id': 'TestTransferNormal',
                'profile': 'local-synthetic-v1', 'dataset_id': 'fixture', 'status': 'PASS', 'failed': False,
                'before': snapshot, 'after': deepcopy(snapshot), 'http_events': [], 'service_logs': [],
                'mysql_log': 'mysql.log', 'metadata': 'metadata.json',
                'assertions': [{'id': 'a1', 'rule_id': 'balance', 'label': 'exact balance',
                                'subject': 'alice/spot/TESTUSD', 'operator': 'eq',
                                'expected': '100', 'actual': '100', 'unit': 'minor:TESTUSD', 'status': 'PASS'}]}

    def test_assertion_result_cannot_lie(self):
        case = self.case_fixture()
        validate_case(case)
        altered = deepcopy(case)
        target = next(a for a in altered['assertions'] if a['rule_id'] == 'balance')
        target['actual'] = '999999999999'
        with self.assertRaises(ProtocolError):
            validate_case(altered)

    def test_gte_does_not_truncate_floats_or_accept_booleans(self):
        for value in [True, 100.5, '100.5', '1e3']:
            case = self.case_fixture()
            case['assertions'][0].update(operator='gte', actual=value)
            case['assertions'][0].pop('unit')
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                validate_case(case)

    def test_boolean_is_not_equal_to_integer(self):
        case = self.case_fixture()
        case['assertions'][0].update(expected=True, actual=1)
        case['assertions'][0].pop('unit')
        with self.assertRaises(ProtocolError):
            validate_case(case)

    def test_managed_run_rejects_symlink_parent_before_creation(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            settings = Settings(root)
            settings.runs.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                settings.job_root('job_' + 'a' * 32)


class RunnerImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(self.tmp.name)
        self.run_id = 'job_' + 'a' * 32
        self.root = self.settings.job_root(self.run_id)
        self.folder = self.root / 'report'
        self.folder.mkdir(parents=True)
        self.catalog = json.loads((Path(C.__file__).parent / 'data/suite-v1.json').read_text())
        suite = self.catalog['suites'][0]
        self.job = {'run_id': self.run_id, 'suite_id': suite['suite_id'], 'suite_version': '1.0.0',
                    'run_kind': 'regression', 'output_dir': str(self.folder)}
        self.report = {'schema_version': '1.0.0', 'document_type': 'leon.qa.run', 'project_id': 'leon-qa-kit',
                       **{k: self.job[k] for k in ['run_id', 'suite_id', 'suite_version', 'run_kind']},
                       'profile': 'local-synthetic-v1', 'status': 'PASS', 'reason': 'fixture', 'exit_code': 0,
                       'started_at': '2026-11-21T00:00:00Z', 'finished_at': '2026-11-21T00:01:00Z',
                       'evidence_dir': str(self.folder), 'source': {'commit': 'fixture', 'dirty': True, 'sha256': 'a' * 64},
                       'required_tests': suite['required_tests'], 'gate_result': {'status': 'PASS', 'exit_code': 0,
                       'reason': 'fixture', 'passed': [suite['package'] + '/' + name for name in suite['required_tests']],
                       'failed': [], 'missing_mandatory': []}, 'cases': [], 'artifacts': [], 'evidence_errors': []}
        for name in suite['required_tests']:
            case = RunnerProtocolTests.case_fixture()
            case.update(run_id=self.run_id, case_id=name)
            relative = 'cases/' + name + '/bundle.json'
            atomic_json(self.folder / relative, case)
            self.report['cases'].append({'case_id': name, 'status': 'PASS', 'evidence_file': relative,
                                         'assertions_passed': 1, 'assertions_failed': 0})
            self.report['artifacts'].append(relative)
        for name in ['metadata.json', 'source-after.json']:
            atomic_json(self.folder / name, {'source': self.report['source']})
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        atomic_json(self.folder / 'summary.json', self.report)
        atomic_json(self.root / 'stdout.json', self.report)

    def load(self, exit_code=0):
        return import_report(self.job, exit_code, self.settings, self.catalog)

    def test_complete_pinned_report_imports(self):
        self.assertEqual(self.load()['status'], 'PASS')

    def test_missing_case_cannot_pass(self):
        self.report['cases'].pop()
        self.save()
        with self.assertRaises(ProtocolError):
            self.load()

    def test_case_summary_cannot_hide_actual_assertions(self):
        self.report['cases'][0]['assertions_passed'] = 999
        self.save()
        with self.assertRaises(ProtocolError):
            self.load()

    def test_exit_code_and_identity_must_match_job(self):
        with self.assertRaises(ProtocolError):
            self.load(exit_code=1)
        self.report['run_id'] = 'foreign_run'
        self.save()
        with self.assertRaises(ProtocolError):
            self.load()

    def test_source_change_prevents_pass(self):
        atomic_json(self.folder / 'source-after.json', {'source': {'sha256': 'b' * 64}})
        with self.assertRaises(ProtocolError):
            self.load()

    def test_stdout_and_saved_report_must_agree(self):
        atomic_json(self.root / 'stdout.json', {**self.report, 'reason': 'different'})
        with self.assertRaises(ProtocolError):
            self.load()

    def test_empty_executed_list_cannot_claim_complete_scope(self):
        self.report['gate_result']['passed'] = []
        self.save()
        with self.assertRaises(ProtocolError):
            self.load()


if __name__ == '__main__':
    unittest.main()
