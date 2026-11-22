"""Only signal verified supervisor groups and remove exact per-job containers."""
import asyncio
import os
from pathlib import Path
import signal
import subprocess
import psutil
from .settings import atomic_json
from .supervisor import child_environment


AUTO_SUPERVISOR = 'app.api.v1.Ntesterc_module.Ntesterc_qa_runner.supervisor'
LAB_SUPERVISOR = 'app.api.v1.Ntesterc_module.Ntesterc_qa_runner.lab_supervisor'


def identity(pid, token, created=None, module=AUTO_SUPERVISOR):
    if module not in {AUTO_SUPERVISOR, LAB_SUPERVISOR}:
        return False
    try:
        process = psutil.Process(pid)
        command = process.cmdline()
        return (process.is_running() and module in command
                and token in command and os.getpgid(pid) == pid
                and (created is None or abs(process.create_time() - created) < 0.02))
    except (psutil.Error, ProcessLookupError, PermissionError):
        return False


def find_supervisor(job, module=AUTO_SUPERVISOR):
    matches = []
    for process in psutil.process_iter(['pid', 'cmdline', 'create_time']):
        command = process.info.get('cmdline') or []
        if job['launch_token'] in command and job['run_id'] in command and identity(process.pid, job['launch_token'], module=module):
            matches.append({'process_pid': process.pid, 'process_created': process.info['create_time']})
    if len(matches) > 1:
        raise RuntimeError('multiple supervisors claim one job; refusing process cleanup')
    return matches[0] if matches else None


async def stop_group(job, module=AUTO_SUPERVISOR):
    pid = job.get('process_pid')
    if not pid:
        return {'process': 'not_started'}
    if not identity(pid, job['launch_token'], job.get('process_created'), module):
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return {'process': 'already_exited'}
        except PermissionError:
            pass
        raise RuntimeError('process group identity cannot be verified; no signal sent')
    os.killpg(pid, signal.SIGTERM)
    await asyncio.sleep(1.5)
    if identity(pid, job['launch_token'], job.get('process_created'), module):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return {'process': 'verified_group_stopped'}


def docker_cleanup(job, registration):
    # A job token is not a credential; it is an unguessable ownership label.
    token, run_id = job['launch_token'], job['run_id']
    env = child_environment(registration, token)
    command = [registration['tools']['docker'], 'ps', '-aq',
               '--filter', 'label=leon.qa.owner=leon-qa-kit',
               '--filter', 'label=leon.qa.run_id=' + run_id,
               '--filter', 'label=leon.qa.job_token=' + token]
    found = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20, check=True).stdout.split()
    removed = []
    for container in found:
        inspection = subprocess.run([registration['tools']['docker'], 'inspect', container],
                                    env=env, capture_output=True, text=True, timeout=15, check=True)
        import json
        labels = json.loads(inspection.stdout)[0]['Config'].get('Labels') or {}
        if labels.get('leon.qa.owner') != 'leon-qa-kit' or labels.get('leon.qa.run_id') != run_id or labels.get('leon.qa.job_token') != token:
            raise RuntimeError('container ownership changed; refusing cleanup')
        result = subprocess.run([registration['tools']['docker'], 'rm', '-f', container], env=env, capture_output=True, text=True, timeout=20)
        if result.returncode and 'No such container' not in result.stderr:
            raise RuntimeError('owned container cleanup failed')
        removed.append(container)
    remaining = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20, check=True).stdout.strip()
    if remaining:
        raise RuntimeError('owned test containers remain')
    return {'matched_containers': found, 'removed_containers': removed, 'remaining': 0}


async def cleanup(job, settings, registration, stop=False, module=AUTO_SUPERVISOR):
    details = {'run_id': job['run_id'], 'errors': []}
    try:
        if stop:
            details.update(await stop_group(job, module))
    except Exception as exc:
        details['errors'].append(type(exc).__name__ + ': ' + str(exc)[:1000])
    try:
        details.update(await asyncio.to_thread(docker_cleanup, job, registration))
    except Exception as exc:
        details['errors'].append(type(exc).__name__ + ': ' + str(exc)[:1000])
    atomic_json(settings.job_root(job['run_id']) / 'cleanup.json', details)
    return details
