"""One long-lived manual Go lab, with an independently verifiable process group."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import psutil
from .lab_paths import LabPaths, child
from .settings import Settings, atomic_json
from .supervisor import child_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--token', required=True)
    args = parser.parse_args()
    folder = LabPaths(Settings(args.runtime)).job_root(args.run_id)
    launch = json.loads(child(folder, 'launch.json').read_text())
    if launch['session_id'] != args.run_id or launch['launch_token'] != args.token:
        raise ValueError('manual environment ownership mismatch')
    binary = child(folder, 'bin', 'qa')
    if hashlib.sha256(binary.read_bytes()).hexdigest() != launch['binary_sha256']:
        raise ValueError('manual environment binary changed')
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    atomic_json(folder / 'supervisor.json', {'pid': os.getpid(), 'process_created': psutil.Process().create_time(),
                                            'run_id': args.run_id, 'launch_token': args.token})
    env = child_environment(launch['registration'], args.token)
    env['QA_RUN_ID'] = args.run_id
    with open(folder / 'service.log', 'xb') as output:
        os.chmod(output.name, 0o600)
        p = subprocess.Popen([str(binary), 'lab', '--listen', '127.0.0.1:0'], cwd=folder, env=env,
                             stdin=subprocess.DEVNULL, stdout=output, stderr=output)
        code = p.wait()
    atomic_json(folder / 'exit.json', {'exit_code': code, 'stopping': stopping, 'run_id': args.run_id})
    while stopping:
        time.sleep(.1)


if __name__ == '__main__':
    main()
