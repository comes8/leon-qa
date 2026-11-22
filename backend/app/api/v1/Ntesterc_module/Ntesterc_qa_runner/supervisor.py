"""Owned process-group leader. Launched only by the independent local worker."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time
import psutil
from .settings import Settings, atomic_json


def child_environment(registration, token):
    allowed = ['HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'GOPROXY', 'GOSUMDB', 'GOPRIVATE',
               'DOCKER_CONFIG', 'TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE']
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    endpoint = registration.get('docker_endpoint', '')
    if not endpoint.startswith('unix:///'):
        raise ValueError('local worker accepts Unix Docker endpoints only')
    env['DOCKER_HOST'] = endpoint
    tools = registration['tools']
    env['PATH'] = os.pathsep.join(dict.fromkeys([str(Path(tools[x]).parent) for x in ['go', 'docker', 'bash']] + ['/usr/bin', '/bin', '/usr/sbin', '/sbin']))
    env['LEON_QA_JOB_TOKEN'] = token
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    settings = Settings(args.runtime)
    folder = settings.job_root(args.run_id)
    import json
    request = json.loads((folder / 'launch.json').read_text())
    if request['run_id'] != args.run_id or request['launch_token'] != args.token:
        raise ValueError('supervisor ownership mismatch')
    registration = settings.registration()
    if registration['root'] != request['toolkit_root']:
        raise ValueError('registration changed before launch')
    if request['run_kind'] not in {'regression', 'selftest'} or request['suite_id'] != 'funds-transfer-v1':
        raise ValueError('unsupported launch request')
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    atomic_json(folder / 'supervisor.json', {'pid': os.getpid(), 'process_created': psutil.Process().create_time(),
                                            'run_id': args.run_id, 'launch_token': args.token})
    command = [registration['tools']['bash'], 'qa.sh', 'test' if request['run_kind'] == 'regression' else 'selftest',
               '--suite', request['suite_id'], '--run-id', args.run_id, '--output-dir', str(folder / 'report')]
    with open(folder / 'stdout.json', 'xb') as stdout, open(folder / 'stderr.log', 'xb') as stderr:
        os.chmod(stdout.name, 0o600)
        os.chmod(stderr.name, 0o600)
        process = subprocess.Popen(command, cwd=registration['root'], stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, env=child_environment(registration, args.token))
        code = process.wait()
    atomic_json(folder / 'exit.json', {'run_id': args.run_id, 'launch_token': args.token, 'exit_code': code,
                                      'supervisor_pid': os.getpid(), 'stopping': stopping})
    # Keep the group leader verifiable until the worker finishes group termination.
    while stopping:
        time.sleep(0.1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
