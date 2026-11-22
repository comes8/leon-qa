"""Single-host durable worker, intentionally separate from the HTTP server."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
from uuid import uuid4
import psutil

from .model import ensure_schema, now
from .processes import cleanup, find_supervisor
from .protocol import SCHEMA_FILE, import_report, read_json, validate
from .settings import ACTIVE, BACKEND_ROOT, Settings, atomic_json
from .store import Store
from .supervisor import child_environment


class Worker:
    def __init__(self, settings, sessions, engine):
        self.settings = settings
        self.store = Store(sessions)
        self.engine = engine
        self.worker_id = uuid4().hex
        self.stopping = asyncio.Event()
        self.active_job = None
        self.active_record = None
        self.created = psutil.Process().create_time()
        self.status = 'starting'
        self.error = None
        self.registration = None
        self.catalog = None

    async def pulse(self):
        while not self.stopping.is_set():
            await self.store.heartbeat(self.worker_id, os.getpid(), self.created, self.status,
                                       self.active_job, self.error)
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    async def register(self):
        self.registration = self.settings.registration()
        root = Path(self.registration['root'])
        if hashlib.sha256((root / 'pkg/report/protocol.schema.json').read_bytes()).digest() != hashlib.sha256(SCHEMA_FILE.read_bytes()).digest():
            raise ValueError('toolkit protocol differs from the pinned worker protocol')
        process = await asyncio.create_subprocess_exec(self.registration['tools']['bash'], 'qa.sh', 'suites',
            cwd=root, env=child_environment(self.registration, ''), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 120)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError('suite catalog build timed out')
        if process.returncode:
            raise RuntimeError('suite catalog build failed: ' + stderr.decode(errors='replace')[-1000:])
        catalog = json.loads(stdout)
        validate(catalog)
        expected = json.loads((Path(__file__).parent / 'data/suite-v1.json').read_text())
        if catalog != expected:
            raise ValueError('registered mandatory suite scope changed')
        self.catalog = catalog
        atomic_json(self.settings.catalog_file, {'registered_root': str(root), 'catalog': catalog,
                                                 'loaded_at': now().isoformat() + 'Z'})

    async def recover(self):
        for job in await self.store.recoverable():
            owned = find_supervisor(job)
            if owned:
                job.update(owned)
            details = await cleanup(job, self.settings, self.registration, stop=bool(job.get('process_pid')))
            state = 'cancelled' if job.get('cancel_requested_at') else 'interrupted'
            changed = await self.store.change(job['id'], ACTIVE | {'completed', 'interrupted', 'timed_out', 'cancelled'},
                {'status': state, 'finished_at': now(), 'result_status': None, 'result': None,
                 'cleanup_status': 'failed' if details['errors'] else 'clean',
                 'error_message': '执行器重启后恢复处理；未自动重跑。' + '; '.join(details['errors'])},
                'recovered', '恢复了中断任务的进程与资源记录，保留原始产物，不自动判为通过')
            if details['errors']:
                raise RuntimeError('recovery cleanup requires attention: ' + job['id'])

    async def end_stopped(self, job, state, message, process=None):
        try:
            current = await self.store.get(job['id'])
        except Exception:
            # Cleanup must still use the in-memory ownership record during DB loss.
            current = None
        if current:
            job = current
        owned = find_supervisor(job)
        if owned:
            job.update(owned)
        details = await cleanup(job, self.settings, self.registration, stop=bool(job.get('process_pid')))
        if process:
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                details['errors'].append('supervisor did not exit after group termination')
        await self.store.change(job['id'], ACTIVE,
            {'status': state, 'finished_at': now(), 'result_status': None,
             'cleanup_status': 'failed' if details['errors'] else 'clean',
             'error_message': message + ('; ' + '; '.join(details['errors']) if details['errors'] else '')},
            state, message)
        if details['errors']:
            raise RuntimeError('owned resource cleanup failed; worker stopped: ' + job['id'])

    async def execute(self, job):
        self.active_job = job['id']
        self.active_record = dict(job)
        self.status = 'running'
        folder = self.settings.job_root(job['run_id'])
        if self.settings.registration()['root'] != job['toolkit_root']:
            await self.store.change(job['id'], {'running'}, {'status': 'completed', 'result_status': 'ENV_ERROR',
                'finished_at': now(), 'cleanup_status': 'not_required', 'error_message': '项目登记在排队后发生变化；未启动进程'},
                'registration_error', '项目登记变化，任务未执行')
            return
        current = await self.store.get(job['id'])
        if current['status'] == 'cancelling':
            await self.end_stopped(job, 'cancelled', '启动前取消任务')
            return
        folder.mkdir(mode=0o700, parents=True, exist_ok=False)
        atomic_json(folder / 'launch.json', {k: job[k] for k in ['id', 'run_id', 'launch_token', 'toolkit_root', 'suite_id', 'run_kind']})
        # Supervisor stays a verifiable session/group leader until cancellation cleanup.
        with open(folder / 'supervisor.log', 'xb') as log:
            os.chmod(log.name, 0o600)
            process = await asyncio.create_subprocess_exec(sys.executable, '-m',
                'app.api.v1.Ntesterc_module.Ntesterc_qa_runner.supervisor', '--runtime', str(self.settings.runtime),
                '--run-id', job['run_id'], '--token', job['launch_token'], cwd=BACKEND_ROOT,
                stdin=asyncio.subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        try:
            created = psutil.Process(process.pid).create_time()
        except psutil.NoSuchProcess:
            created = None
        self.active_record.update(process_pid=process.pid, process_created=created)
        await self.store.change(job['id'], ACTIVE, {'process_pid': process.pid, 'process_created': created},
                                'process_started', '已启动本任务专属进程组')
        job = await self.store.get(job['id'])
        started = time.monotonic()
        while process.returncode is None:
            current = await self.store.get(job['id'])
            if current['status'] == 'cancelling':
                await self.end_stopped(current, 'cancelled', '取消请求已处理', process)
                return
            if self.stopping.is_set():
                await self.end_stopped(current, 'interrupted', '执行器停止，任务中断并保留产物', process)
                return
            if time.monotonic() - started >= job['timeout_seconds']:
                await self.end_stopped(current, 'timed_out', '任务超过允许执行时间', process)
                return
            await asyncio.sleep(0.2)
        current = await self.store.get(job['id'])
        if current['status'] == 'cancelling':
            await self.end_stopped(current, 'cancelled', '结果导入前收到取消请求', process)
            return
        result, error, exit_code = None, None, process.returncode
        verified_exit = False
        try:
            if process.returncode != 0:
                raise ValueError('supervisor terminated unexpectedly')
            exited = read_json(folder / 'exit.json')
            if exited['run_id'] != job['run_id'] or exited['launch_token'] != job['launch_token'] or exited['stopping']:
                raise ValueError('supervisor exit evidence mismatch')
            verified_exit = True
            exit_code = exited['exit_code']
            result = import_report(job, exit_code, self.settings, self.catalog)
        except Exception as exc:
            error = '报告导入失败：' + type(exc).__name__ + ': ' + str(exc)[:1500]
        details = await cleanup(job, self.settings, self.registration, stop=not verified_exit)
        if details['errors']:
            error = (error or '') + '; 资源核对失败：' + '; '.join(details['errors'])
        changed = await self.store.change(job['id'], {'running'}, {'status': 'completed', 'finished_at': now(),
            'result': None if error else result, 'result_status': 'ENV_ERROR' if error else result['status'],
            'process_exit_code': exit_code, 'cleanup_status': 'failed' if details['errors'] else 'clean',
            'error_message': error}, 'completed', '执行结束，已核对退出码、报告身份、协议与证据')
        if not changed:
            await self.end_stopped(job, 'cancelled', '结果提交前收到取消请求')
        if details['errors']:
            raise RuntimeError('resource cleanup failed; refusing further jobs')

    async def run(self):
        self.settings.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = open(self.settings.runtime / 'worker.lock', 'a+')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError('a local worker already owns this runtime')
        pulse = None
        lab_task = None
        try:
            await ensure_schema(self.engine)
            pulse = asyncio.create_task(self.pulse())
            await self.register()
            await self.recover()
            from .lab_worker import LabManager
            lab_manager = LabManager(self.settings, self.store.sessions, self.stopping)
            lab_task = asyncio.create_task(lab_manager.run())
            ready = asyncio.create_task(lab_manager.ready.wait())
            try:
                await asyncio.wait({lab_task, ready}, return_when=asyncio.FIRST_COMPLETED)
                if lab_task.done():
                    await lab_task
                    raise RuntimeError('manual recovery ended before readiness')
                await ready
            finally:
                if not ready.done():
                    ready.cancel()
                    await asyncio.gather(ready, return_exceptions=True)
            self.status = 'idle'
            while not self.stopping.is_set():
                if lab_task.done():
                    await lab_task
                    raise RuntimeError('manual lab manager stopped unexpectedly')
                if pulse.done():
                    await pulse
                    raise RuntimeError('worker heartbeat stopped unexpectedly')
                job = await self.store.claim(self.worker_id)
                if job:
                    await self.execute(job)
                    self.active_job, self.status = None, 'idle'
                    self.active_record = None
                else:
                    await asyncio.sleep(0.25)
        except Exception as exc:
            self.status, self.error = 'blocked', str(exc)[:2000]
            if self.active_record:
                job = self.active_record
                if job['status'] in ACTIVE:
                    try:
                        await self.end_stopped(job, 'interrupted', '执行器异常退出，保留失败记录')
                    except Exception as cleanup_error:
                        self.error += '; ' + str(cleanup_error)[:1000]
            raise
        finally:
            self.stopping.set()
            try:
                if lab_task:
                    try:
                        await lab_task
                    except Exception as exc:
                        self.status, self.error = 'blocked', 'manual lab manager: ' + str(exc)[:1500]
                if pulse:
                    try:
                        await pulse
                    except Exception as exc:
                        self.status, self.error = 'blocked', 'heartbeat failed: ' + str(exc)[:1500]
                await self.store.heartbeat(self.worker_id, os.getpid(), self.created,
                                           self.status if self.status == 'blocked' else 'stopped', self.active_job, self.error)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime')
    args = parser.parse_args()
    from app.core.database import async_session_factory, engine
    worker = Worker(Settings(args.runtime), async_session_factory, engine)
    loop = asyncio.get_running_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, worker.stopping.set)
    try:
        await worker.run()
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
