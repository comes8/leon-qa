#!/usr/bin/env python
"""One local operator entry. Fixed services only; never called by a web request."""
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import psutil

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
RUNTIME = ROOT / '.runtime'
sys.path.insert(0, str(BACKEND))
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.settings import Settings, atomic_json
from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.supervisor import child_environment


def specification(name):
    if name == 'backend':
        return BACKEND, [str(BACKEND / '.venv/bin/python'), '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '18171'], 18171, '/openapi.json'
    node = shutil.which('node')
    if not node:
        raise RuntimeError('未找到已有 Node.js，请检查本机 PATH')
    return ROOT / 'frontend', [node, str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '18170', '--strictPort'], 18170, '/'


def identity(name, record, legacy=False):
    try:
        cwd, command, _, _ = specification(name)
        p = psutil.Process(record['pid'])
        args = p.cmdline()
        return (p.is_running() and p.status() != psutil.STATUS_ZOMBIE and p.cwd() == str(cwd)
                and args[1:] == command[1:] and Path(p.exe()).resolve() == Path(command[0]).resolve()
                and (legacy or abs(p.create_time() - record['process_created']) < .02))
    except (psutil.Error, KeyError, IndexError, OSError, RuntimeError, TypeError):
        return False


def load_record(name):
    path = RUNTIME / (name + '-process.json')
    if path.is_symlink():
        raise RuntimeError('进程记录路径异常，未执行进程操作')
    if path.exists():
        return json.loads(path.read_text())
    legacy = RUNTIME / (name + '.pid')
    try:
        value = {'pid': int(legacy.read_text())}
        if identity(name, value, legacy=True):
            value['process_created'] = psutil.Process(value['pid']).create_time()
            return value
    except (ValueError, OSError, psutil.Error):
        pass
    return {}


def reachable(port, path):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def occupied(port):
    with socket.socket() as connection:
        connection.settimeout(.3)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def owns_listener(name, record):
    if not identity(name, record):
        return False
    _, _, port, _ = specification(name)
    try:
        values = subprocess.check_output(['lsof', '-nP', '-a', '-p', str(record['pid']),
            '-iTCP:' + str(port), '-sTCP:LISTEN', '-t'], stderr=subprocess.DEVNULL, timeout=3, text=True).split()
        return str(record['pid']) in values
    except Exception:
        return False


def service_state(name):
    _, _, port, path = specification(name)
    record = load_record(name)
    owned = bool(record) and identity(name, record)
    listener = owns_listener(name, record)
    ready = reachable(port, path)
    return {'id': name, 'status': 'healthy' if owned and listener and ready else 'conflict' if occupied(port) and not listener else 'starting' if owned else 'offline',
            'owned_process': owned, 'pid': record.get('pid') if owned else None, 'port': port}


def start_service(name):
    cwd, command, port, path = specification(name)
    record = load_record(name)
    if identity(name, record):
        atomic_json(RUNTIME / (name + '-process.json'), record)
    else:
        if occupied(port):
            raise RuntimeError(f'{name} 端口{port}被非所属进程占用，未停止该进程')
        if any((RUNTIME / (name + suffix)).is_symlink() for suffix in ['.log', '.pid']):
            raise RuntimeError('日志或进程指针路径异常，未启动服务')
        with open(RUNTIME / (name + '.log'), 'ab') as log:
            os.chmod(log.name, 0o600)
            p = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        record = {'pid': p.pid, 'process_created': psutil.Process(p.pid).create_time()}
        atomic_json(RUNTIME / (name + '-process.json'), record)
        (RUNTIME / (name + '.pid')).write_text(str(p.pid) + '\n')
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not identity(name, record):
            raise RuntimeError(f'{name}已退出，请查看.runtime/{name}.log')
        if owns_listener(name, record) and reachable(port, path):
            return service_state(name)
        time.sleep(.25)
    raise RuntimeError(f'{name}尚未就绪，请查看.runtime/{name}.log；原记录已保留')


def stop_service(name):
    record = load_record(name)
    if not identity(name, record):
        return {'id': name, 'stopped': True, 'detail': '无可验证的所属进程，未发送信号'}
    p = psutil.Process(record['pid'])
    group = os.getpgid(p.pid) == p.pid
    if group:
        os.killpg(p.pid, signal.SIGTERM)
    else:
        p.send_signal(signal.SIGTERM)
    deadline = time.monotonic() + 20
    while identity(name, record) and time.monotonic() < deadline:
        time.sleep(.2)
    if identity(name, record):
        if group and os.getpgid(p.pid) == p.pid:
            os.killpg(p.pid, signal.SIGKILL)
        else:
            p.kill()
        try:
            p.wait(timeout=5)
        except psutil.TimeoutExpired:
            raise RuntimeError(f'{name}停止未完成，未继续重启')
    return {'id': name, 'stopped': True}


def worker(action):
    result = subprocess.run([sys.executable, str(BACKEND / 'scripts/qa_runner.py'), action], cwd=BACKEND,
                            capture_output=True, text=True, timeout=110)
    if result.returncode:
        raise RuntimeError(f'执行器{action}未完成；请查看.runtime/qa-runner/worker.log')
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    if action == 'start':
        from app.core.database import engine, async_session_factory
        from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.store import Store
        from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.health import verified_worker
        async def ready():
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    state = await Store(async_session_factory).health()
                    if state['status'] in {'idle', 'running'} and verified_worker(state, Settings()):
                        return state
                    if state['status'] == 'blocked':
                        raise RuntimeError('执行器异常阻塞；先检查所属资源清理和执行器日志')
                    await asyncio.sleep(.25)
                raise RuntimeError('执行器仍在启动或恢复中；请查看status，不要重复启动')
            finally:
                await engine.dispose()
        receipt.update(asyncio.run(ready()))
    return receipt


def prepare_dependencies():
    reg = Settings().registration()
    env = child_environment(reg, '')
    def docker(*args, timeout=15):
        return subprocess.check_output([reg['tools']['docker'], *args], env=env, stderr=subprocess.DEVNULL, text=True, timeout=timeout)
    try:
        docker('info', '--format', '{{.ServerVersion}}', timeout=5)
    except Exception:
        raise RuntimeError('已登记本机Docker不可用。请先启动Docker Desktop，再执行 ./leonqa start；不会回退到其他Docker服务')
    # Only existing dependency containers. Never create a blank replacement database.
    for name, image, exposed, port in [('ntester-local-mysql', 'mysql:8.0.45', '3306/tcp', '13389'),
                                        ('ntester-local-redis', 'redis:6.0-alpine', '6379/tcp', '16389')]:
        try:
            container = json.loads(docker('inspect', name))[0]
        except Exception:
            raise RuntimeError(f'未找到已安装的{name}；未创建新库，请按运维手册恢复本机依赖')
        bindings = container['HostConfig'].get('PortBindings') or {}
        if container['Config']['Image'] != image or bindings.get(exposed) != [{'HostIp': '127.0.0.1', 'HostPort': port}]:
            raise RuntimeError(f'{name}镜像或本机端口不匹配，未启动未知依赖')
        if name.endswith('mysql') and not any(m.get('Name') == 'ntester-local-mysql-data' and m['Destination'] == '/var/lib/mysql' for m in container['Mounts']):
            raise RuntimeError('平台数据库卷不匹配，未启动替代数据库')
        if not container['State']['Running']:
            docker('start', name, timeout=40)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            docker('exec', 'ntester-local-mysql', 'mysqladmin', 'ping', '--protocol=tcp', '-h', '127.0.0.1', '--silent', timeout=3)
            if docker('exec', 'ntester-local-redis', 'redis-cli', 'ping', timeout=3).strip() == 'PONG':
                return
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError('平台依赖未就绪，未启动执行器')


def inspect_stack():
    from app.api.v1.Ntesterc_module.Ntesterc_qa_runner.health import collect
    from app.core.database import engine
    async def probe():
        try:
            return await collect()
        finally:
            await engine.dispose()
    report = asyncio.run(probe())
    report['services'] = [service_state(n) for n in ['backend', 'frontend']]
    if any(s['status'] != 'healthy' for s in report['services']):
        report['overall'] = 'degraded'
    return report


def main():
    parser = argparse.ArgumentParser(description='Leon QA 本机管理；停止应用保留数据库、历史和日志')
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'doctor'])
    parser.add_argument('target', nargs='?', default='all', choices=['all', 'backend', 'frontend', 'worker'])
    args = parser.parse_args()
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    if args.action in {'status', 'doctor'}:
        report = inspect_stack()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if args.action == 'status' or report['overall'] == 'ready' else 2
    with open(RUNTIME / 'stack.lock', 'a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('另一条启停操作仍在进行，请等待其结果')
        results = []
        if args.action in {'stop', 'restart'}:
            if args.target in {'all', 'worker'}:
                results.append({'worker': worker('stop')})
            for name in ['backend', 'frontend']:
                if args.target in {'all', name}:
                    results.append(stop_service(name))
        if args.action in {'start', 'restart'}:
            prepare_dependencies()
            for name in ['backend', 'frontend']:
                if args.target in {'all', name}:
                    results.append(start_service(name))
            if args.target in {'all', 'worker'}:
                results.append({'worker': worker('start')})
        print(json.dumps({'action': args.action, 'target': args.target, 'results': results,
            'note': '启停只处理所属应用进程；平台数据库/Redis容器与所有历史、日志继续保留'}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        # These messages are fixed operator guidance from this controller.
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(2)
    except Exception:
        # Errors must never echo DSNs, environment values, or subprocess argv.
        print(json.dumps({'ok': False, 'error': '本机管理操作未完成；请运行 ./leonqa status 并检查运维手册及对应日志。'}, ensure_ascii=False))
        raise SystemExit(2)
