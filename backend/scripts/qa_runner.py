#!/usr/bin/env python
"""Local operator control; never exposed as an HTTP command runner."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import psutil

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import Settings, atomic_json

MODULE = 'app.api.v1.Ntesterc_module.Ntesterc_qa_runner.worker'


def owned(info, settings):
    try:
        p = psutil.Process(info['pid'])
        args = p.cmdline()
        return MODULE in args and str(settings.runtime) in args and abs(p.create_time() - info['process_created']) < 0.02
    except (psutil.Error, KeyError):
        return False


async def health():
    from app.core.database import async_session_factory, engine
    from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.store import Store
    from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.model import ensure_schema
    await ensure_schema(engine)
    try:
        return await Store(async_session_factory).health()
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['configure', 'init', 'start', 'stop', 'status'])
    parser.add_argument('--project-root')
    parser.add_argument('--runtime')
    args = parser.parse_args()
    settings = Settings(args.runtime)
    pidfile = settings.runtime / 'worker-process.json'
    if args.action == 'configure':
        if not args.project_root:
            parser.error('configure requires --project-root')
        settings.configure(args.project_root)
        print(json.dumps({'configured': True, 'project_key': 'leon-qa-kit', 'runtime': str(settings.runtime)}))
        return
    if args.action in {'init', 'status'}:
        print(json.dumps(asyncio.run(health()), ensure_ascii=False))
        return
    info = json.loads(pidfile.read_text()) if pidfile.exists() else {}
    if args.action == 'stop':
        if not owned(info, settings):
            print(json.dumps({'stopped': True, 'message': 'no verified worker process running'}))
            return
        os.kill(info['pid'], signal.SIGTERM)
        deadline = time.monotonic() + 45
        while owned(info, settings) and time.monotonic() < deadline:
            time.sleep(0.2)
        if owned(info, settings):
            raise RuntimeError('worker is still stopping; inspect worker.log before restarting')
        print(json.dumps({'stopped': True}))
        return
    settings.registration()
    settings.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    if owned(info, settings):
        print(json.dumps({'already_running': True, 'pid': info['pid']}))
        return
    with open(settings.runtime / 'worker.log', 'ab') as log:
        os.chmod(log.name, 0o600)
        p = subprocess.Popen([sys.executable, '-m', MODULE, '--runtime', str(settings.runtime)], cwd=BACKEND,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    info = {'pid': p.pid, 'process_created': psutil.Process(p.pid).create_time()}
    atomic_json(pidfile, info)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if p.poll() is not None:
            raise RuntimeError('worker exited during startup; inspect worker.log')
        state = asyncio.run(health())
        if state.get('pid') == p.pid and state['status'] in {'idle', 'running'}:
            print(json.dumps({'started': True, **state}, ensure_ascii=False))
            return
        if state.get('pid') == p.pid and state['status'] == 'blocked':
            raise RuntimeError(state.get('last_error') or 'worker blocked')
        time.sleep(0.25)
    raise RuntimeError('worker startup timed out; inspect worker.log')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(2)
