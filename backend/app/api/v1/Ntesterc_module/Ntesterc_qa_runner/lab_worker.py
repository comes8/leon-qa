"""Manual data preparation through the registered Go CLI, in per-environment cwd."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
from urllib.parse import urlparse
import httpx
import psutil
from .lab_model import LabDataset, LabEnvironment, LabOperation
from .lab_paths import LabPaths, child, source_digest
from .lab_store import LabStore
from .model import now
from .processes import LAB_SUPERVISOR, cleanup, find_supervisor, identity
from .settings import BACKEND_ROOT, atomic_json
from .supervisor import child_environment


def snapshot_public(value):
    if isinstance(value, list):
        return [snapshot_public(v) for v in value]
    if isinstance(value, dict):
        return {k: str(v) if k.endswith('_minor') and isinstance(v, int) else snapshot_public(v) for k, v in value.items()}
    return value


class LabManager:
    def __init__(self, settings, sessions, stopping):
        self.settings, self.stopping = settings, stopping
        self.store = LabStore(sessions)
        self.paths = LabPaths(settings)
        self.owned = {}
        self.ready = asyncio.Event()
        self.health_failures = {}
        self.next_health_check = 0

    def process_record(self, env):
        return dict(env, run_id=env['session_id'])

    async def command(self, args, cwd, env, timeout=30, log=None):
        process = await asyncio.create_subprocess_exec(*map(str, args), cwd=cwd, env=env,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True)
        created = psutil.Process(process.pid).create_time()
        waiting = asyncio.create_task(process.communicate()); start = time.monotonic()
        try:
            while not waiting.done():
                if self.stopping.is_set() or time.monotonic() - start > timeout:
                    raise RuntimeError('local command stopped or timed out; result is not trusted')
                await asyncio.wait({waiting}, timeout=.15)
            out, err = await waiting
            if log:
                log.write_bytes(err)
                os.chmod(log, 0o600)
            if process.returncode:
                raise RuntimeError('registered Go operation returned a nonzero exit code')
            return out
        finally:
            if process.returncode is None:
                try:
                    p = psutil.Process(process.pid)
                    if abs(p.create_time() - created) < .02 and os.getpgid(p.pid) == p.pid:
                        os.killpg(p.pid, signal.SIGKILL)
                except (psutil.Error, ProcessLookupError):
                    pass
                await process.wait()
            if not waiting.done():
                await waiting

    async def close(self, env, status='stopped', message=None):
        job = self.process_record(env)
        if env.get('active_slot') is None and env.get('cleanup_status') == 'clean':
            job['process_pid'] = None
            job['process_created'] = None
        found = find_supervisor(job, LAB_SUPERVISOR)
        if found:
            job.update(found)
        details = await cleanup(job, self.paths, env['registration'], stop=bool(job.get('process_pid')), module=LAB_SUPERVISOR)
        await self.store.retire(env['id'], status if not details['errors'] else 'error', not details['errors'],
                                message or ('; '.join(details['errors']) if details['errors'] else None))
        if details['errors']:
            raise RuntimeError('manual environment cleanup could not be verified')
        self.owned.pop(env['id'], None)
        self.health_failures.pop(env['id'], None)
        return details

    def base(self, env):
        if not identity(env.get('process_pid'), env['launch_token'], env.get('process_created'), LAB_SUPERVISOR):
            raise RuntimeError('manual lab supervisor is unavailable')
        folder = self.paths.job_root(env['session_id'])
        descriptor = json.loads(child(folder, '.runtime', 'lab.json').read_text())
        base = descriptor.get('base_url', '')
        u = urlparse(base)
        if u.scheme != 'http' or u.hostname != '127.0.0.1' or not u.port or u.path or u.query or u.fragment or u.username:
            raise ValueError('manual lab must use its assigned loopback endpoint')
        if not re.fullmatch(r'[a-f0-9]{64}', descriptor.get('container_id', '')):
            raise ValueError('invalid lab container identity')
        return base, descriptor['container_id']

    async def start(self, op, env):
        folder = self.paths.job_root(env['session_id'])
        folder.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.owned[env['id']] = env
        registration = env['registration']; runtime_env = child_environment(registration, env['launch_token'])
        before = await asyncio.to_thread(source_digest, registration['root'])
        binary = child(folder, 'bin', 'qa'); binary.parent.mkdir(mode=0o700)
        await self.store.patch(LabEnvironment, env['id'], {'status': 'starting', 'cleanup_status': 'pending'})
        await self.command([registration['tools']['go'], 'build', '-o', binary, './cmd/qa'], registration['root'],
                           runtime_env, timeout=120, log=folder / 'build.log')
        if before != await asyncio.to_thread(source_digest, registration['root']):
            raise RuntimeError('toolkit sources changed during manual lab build')
        atomic_json(folder / 'launch.json', {'session_id': env['session_id'], 'launch_token': env['launch_token'],
            'registration': registration, 'source_sha256': before, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()})
        with open(folder / 'supervisor.log', 'xb') as log:
            os.chmod(log.name, 0o600)
            p = await asyncio.create_subprocess_exec(sys.executable, '-m', LAB_SUPERVISOR, '--runtime', str(self.settings.runtime),
                '--run-id', env['session_id'], '--token', env['launch_token'], cwd=BACKEND_ROOT,
                stdin=asyncio.subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        env.update(process_pid=p.pid, process_created=psutil.Process(p.pid).create_time(), source_sha256=before)
        self.owned[env['id']] = env
        await self.store.patch(LabEnvironment, env['id'], {k: env[k] for k in ['process_pid', 'process_created', 'source_sha256']})
        deadline = time.monotonic() + 120
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=2) as client:
            while time.monotonic() < deadline and not self.stopping.is_set():
                if p.returncode is not None:
                    raise RuntimeError('manual lab process exited during startup')
                try:
                    base, container_id = self.base(env)
                    response = await client.get(base + '/healthz')
                    if response.status_code == 200 and response.json().get('profile') == 'local-synthetic-v1':
                        labels = json.loads(await self.command([registration['tools']['docker'], 'inspect', '--format',
                            '{{json .Config.Labels}}', container_id], folder, runtime_env))
                        expected = {'leon.qa.owner': 'leon-qa-kit', 'leon.qa.run_id': env['session_id'], 'leon.qa.job_token': env['launch_token']}
                        if any(labels.get(k) != v for k, v in expected.items()):
                            raise RuntimeError('manual container labels do not match environment')
                        await self.store.patch(LabEnvironment, env['id'], {'status': 'running', 'error_message': None})
                        self.health_failures[env['id']] = 0
                        atomic_json(folder / 'health.json', {'status': 'healthy', 'consecutive_failures': 0,
                            'checked_at': now().isoformat() + 'Z'})
                        return {'environment_id': env['id'], 'status': 'running', 'source_sha256': before}
                except (FileNotFoundError, httpx.HTTPError, json.JSONDecodeError):
                    pass
                await asyncio.sleep(.2)
        raise RuntimeError('manual environment startup was interrupted or timed out')

    async def data(self, op, env):
        dataset = await self.store.get(LabDataset, op['dataset_id'])
        folder = self.paths.job_root(env['session_id']); base, _ = self.base(env)
        opdir = child(folder, 'operations', op['id']); opdir.mkdir(parents=True, mode=0o700)
        runtime_env = child_environment(env['registration'], env['launch_token'])
        binary = child(folder, 'bin', 'qa')
        launch = json.loads(child(folder, 'launch.json').read_text())
        if hashlib.sha256(binary.read_bytes()).hexdigest() != launch['binary_sha256']:
            raise RuntimeError('manual environment binary changed since startup')
        generation = dataset['generation']
        old_file = child(folder, 'states', dataset['id'], str(generation), 'current.json')
        action = op['action']
        from .debug_worker import DEBUG_ACTIONS, execute_debug
        if action in DEBUG_ACTIONS:
            return await execute_debug(self, op, env, dataset, folder, binary, base, old_file, opdir, runtime_env)
        history = list(dataset['history'] or [])
        before = dataset['snapshot']
        if action in {'delete', 'rebuild'} and dataset['native_id']:
            args = [binary, 'state', 'delete', '--base', base, '--file', old_file]
            await self.command(args, folder, runtime_env, log=opdir / 'delete.log')
            history.append({'generation': generation, 'native_id': dataset['native_id'], 'snapshot': before,
                            'reason': action, 'operation_id': op['id'], 'at': now().isoformat() + 'Z'})
            await self.store.patch(LabDataset, dataset['id'], {'native_id': None, 'history': history})
        if action in {'create', 'rebuild'}:
            generation += 1
            target = child(folder, 'states', dataset['id'], str(generation), 'current.json')
            args = [binary, 'state', 'create', '--base', base, '--file', target, '--name', dataset['name'],
                    '--funding', dataset['funding'], '--spot', dataset['spot'], '--run-id', env['session_id']]
            raw = json.loads(await self.command(args, folder, runtime_env, log=opdir / 'create.log'))
            native = raw['dataset_id']; snap = snapshot_public(raw['snapshot'])
        elif action == 'inspect':
            snap = snapshot_public(json.loads(await self.command([binary, 'state', 'inspect', '--base', base,
                '--file', old_file], folder, runtime_env, log=opdir / 'inspect.log')))
            native = dataset['native_id']
        else:
            snap, native = before, None
        if action != 'delete' and (not native or snap.get('dataset_id') != native):
            raise RuntimeError('snapshot belongs to another dataset')
        result = {'dataset_id': dataset['id'], 'native_id': native, 'generation': generation,
                  'status': 'deleted' if action == 'delete' else 'ready', 'snapshot': snap,
                  'observation': 'registered Go SDK / local repeatable-read snapshot', 'operation_id': op['id']}
        atomic_json(opdir / 'result.json', result)
        await self.store.patch(LabDataset, dataset['id'], {'native_id': native, 'generation': generation,
            'status': result['status'], 'snapshot': snap, 'history': history, 'error_message': None,
            'revision': dataset['revision'] + 1})
        return result

    async def execute(self, op):
        env = await self.store.get(LabEnvironment, op['environment_id'])
        try:
            if op['action'] == 'start':
                result = await self.start(op, env)
            elif op['action'] == 'stop':
                result = {'environment_id': env['id'], 'status': 'stopped', 'cleanup': await self.close(env)}
            else:
                result = await self.data(op, env)
            await self.store.finish(op, result=result)
        except Exception as error:
            folder = self.paths.job_root(env['session_id']); folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_json(folder / ('error-' + op['id'] + '.json'), {'error': type(error).__name__, 'message': str(error)[:2000]})
            if op['action'] in {'transfer', 'query', 'verify'} and identity(env.get('process_pid'), env['launch_token'], env.get('process_created'), LAB_SUPERVISOR):
                # A crashed CLI may have committed a transfer. Keep the environment for original-ID query.
                row = await self.store.get(LabDataset, op['dataset_id'])
                await self.store.patch(LabDataset, row['id'], {'status': 'ready', 'revision': row['revision'] + 1,
                    'error_message': '调试结果未知；先按原请求号查询，勿换号重试。最后快照可能过期。'})
                await self.store.finish(op, result={'verdict': 'UNKNOWN', 'outcome': 'UNKNOWN',
                    'request_id': op['inputs']['business_request_id'], 'action': op['action'],
                    'associations': {k: op['inputs'][k] for k in ['requirement_ref', 'case_ref', 'review_note'] if k in op['inputs']}},
                    error='调试未取得可信回执；保留环境，先按原请求号查询。')
                return
            cleanup_error = None
            try:
                await self.close(self.owned.get(env['id'], env), 'error', '本地操作异常，环境已回收；保留快照，请重新启动环境')
            except Exception as exc:
                cleanup_error = str(exc)
            await self.store.finish(op, error='本地操作未完成，不能视为成功。' + ('资源归属清理需人工检查。' if cleanup_error else '环境已回收，历史快照保留。'))
            if cleanup_error:
                raise RuntimeError(cleanup_error)

    async def monitor(self):
        if time.monotonic() < self.next_health_check:
            return
        self.next_health_check = time.monotonic() + 2
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=1.5) as client:
            for env in await self.store.environments():
                if env['status'] != 'running':
                    continue
                if not identity(env.get('process_pid'), env['launch_token'], env.get('process_created'), LAB_SUPERVISOR):
                    await self.close(env, 'interrupted', '手工环境进程已退出，资源已核对，快照保留')
                    continue
                healthy = False
                try:
                    base, _ = self.base(env)
                    response = await client.get(base + '/healthz')
                    healthy = response.status_code == 200 and response.json().get('profile') == 'local-synthetic-v1'
                except (OSError, ValueError, RuntimeError, httpx.HTTPError):
                    pass
                failures = 0 if healthy else self.health_failures.get(env['id'], 0) + 1
                self.health_failures[env['id']] = failures
                atomic_json(self.paths.job_root(env['session_id']) / 'health.json', {
                    'status': 'healthy' if healthy else 'degraded', 'consecutive_failures': failures,
                    'checked_at': now().isoformat() + 'Z'})
                if failures >= 3:
                    await self.close(env, 'interrupted', '手工环境连续三次健康检查失败，已回收所属资源；历史快照保留')

    async def run(self):
        try:
            for env in await self.store.environments():
                self.owned[env['id']] = env
                await self.close(env, 'interrupted', '执行器重启，旧手工环境已回收；未自动重建数据')
            await self.store.recover_operations()
            self.ready.set()
            while not self.stopping.is_set():
                op = await self.store.claim()
                if op:
                    await self.execute(op)
                else:
                    await self.monitor()
                    await asyncio.sleep(.4)
        finally:
            failures = []
            for env in list(self.owned.values()):
                try:
                    await self.close(env, 'stopped', '执行器停止，所属手工环境已关闭，快照保留')
                except Exception:
                    failures.append(env['id'])
            if failures:
                raise RuntimeError('manual cleanup requires attention for ' + ','.join(failures))
