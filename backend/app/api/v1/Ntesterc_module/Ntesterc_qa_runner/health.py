"""Read-only, bounded local diagnostics. Never return connection strings or commands."""
import asyncio
import json
from datetime import datetime
import psutil
from sqlalchemy import text
from .model import now
from .settings import Settings
from .store import Store
from .supervisor import child_environment


def item(identity, label, healthy, detail):
    return {'id': identity, 'label': label, 'status': 'healthy' if healthy else 'degraded', 'detail': detail}


def verified_worker(value, settings):
    try:
        record = json.loads((settings.runtime / 'worker-process.json').read_text())
        process = psutil.Process(record['pid'])
        return (value.get('pid') == process.pid
                and process.status() not in {psutil.STATUS_ZOMBIE, psutil.STATUS_STOPPED}
                and abs(process.create_time() - record['process_created']) < .02
                and 'app.api.v1.Ntesterc_module.Ntesterc_qa_runner.worker' in process.cmdline()
                and str(settings.runtime) in process.cmdline())
    except (OSError, ValueError, KeyError, psutil.Error):
        return False


async def collect(settings=None):
    from app.core.database import engine, async_session_factory
    from app.config.setting import config
    from redis import asyncio as redis
    settings = settings or Settings()

    async def database():
        try:
            async with asyncio.timeout(2):
                async with engine.connect() as connection:
                    await connection.execute(text('SELECT 1'))
            return item('database', '平台数据库', True, '只读连接检查正常')
        except Exception:
            return item('database', '平台数据库', False, '连接失败或超时，请检查本机数据库及配置')

    async def cache():
        client = None
        try:
            client = redis.from_url(config.REDIS_URI, socket_connect_timeout=1, socket_timeout=1)
            await asyncio.wait_for(client.ping(), 2)
            return item('redis', '平台 Redis', True, 'PING 正常')
        except Exception:
            return item('redis', '平台 Redis', False, '连接失败或超时，请检查本机 Redis')
        finally:
            if client:
                try:
                    await asyncio.wait_for(client.aclose(), 1)
                except Exception:
                    pass

    async def docker():
        process = None
        try:
            reg = settings.registration()
            process = await asyncio.create_subprocess_exec(reg['tools']['docker'], 'info', '--format', '{{.ServerVersion}}',
                env=child_environment(reg, ''), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(process.wait(), 3)
            return item('docker', '已登记本机 Docker', process.returncode == 0,
                        '本机服务可用' if process.returncode == 0 else '本机服务不可用，请启动 Docker 后重试')
        except Exception:
            return item('docker', '已登记本机 Docker', False, '服务不可用或尚未登记，不尝试远端回退')
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

    async def worker():
        try:
            value = await asyncio.wait_for(Store(async_session_factory).health(), 2)
            if value['status'] in {'idle', 'running', 'starting'} and not verified_worker(value, settings):
                value['status'] = 'offline'
            good = value['status'] in {'idle', 'running'}
            label = {'idle': '空闲待命', 'running': '执行中', 'starting': '启动或恢复中', 'blocked': '异常阻塞', 'offline': '离线'}.get(value['status'], value['status'])
            return item('worker', '本地执行器', good, label), value['status']
        except Exception:
            return item('worker', '本地执行器', False, '无法取得心跳，先检查平台数据库'), 'unknown'

    async def toolkit():
        try:
            settings.registration()
            settings.catalog()
            return item('toolkit', 'Go 工具包登记', True, '本机路径、固定套件及工具可读取')
        except Exception:
            return item('toolkit', 'Go 工具包登记', False, '未登记或文件不可用，请按运维手册配置')

    db, red, dock, work, kit = await asyncio.gather(database(), cache(), docker(), worker(), toolkit())
    checks = [db, red, dock, work[0], kit]
    return {'overall': 'ready' if all(c['status'] == 'healthy' for c in checks) else 'degraded',
            'checked_at': now().isoformat() + 'Z', 'worker_status': work[1], 'checks': checks,
            'scope': '本机只读诊断；健康不代表业务测试通过'}


async def for_project(project, user):
    from app.core.database import async_session_factory
    from .lab_store import LabStore
    from .lab_paths import LabPaths, child
    data = await collect()
    listing = await LabStore(async_session_factory).listing(project, user)
    data['environments'] = []
    for env in listing['environments']:
        if env['status'] not in {'running', 'starting', 'stopping', 'error'}:
            continue
        state = {'id': env['id'], 'status': env['status'], 'cleanup_status': env['cleanup_status']}
        if env['status'] == 'running':
            try:
                p = child(LabPaths(Settings()).job_root(env['session_id']), 'health.json')
                health = json.loads(p.read_text())
                age = (now() - datetime.fromisoformat(health['checked_at'].rstrip('Z'))).total_seconds()
                state['probe'] = 'healthy' if health['status'] == 'healthy' and age < 20 else 'degraded'
                state['checked_at'] = health['checked_at']
                state['consecutive_failures'] = health['consecutive_failures']
            except Exception:
                state['probe'] = 'unknown'
        data['environments'].append(state)
    if any(e['status'] != 'running' or e.get('probe') in {'degraded', 'unknown'} or e['cleanup_status'] == 'failed' for e in data['environments']):
        data['overall'] = 'degraded'
    return data
