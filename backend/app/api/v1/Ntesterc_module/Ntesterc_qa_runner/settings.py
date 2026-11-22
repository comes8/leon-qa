"""Operator-owned local registration. HTTP requests cannot override these paths."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PLATFORM_ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'backend/pyproject.toml').is_file())
BACKEND_ROOT = PLATFORM_ROOT / 'backend'
PROJECT_KEY = 'leon-qa-kit'
SUITE_ID = 'funds-transfer-v1'
TERMINAL = {'completed', 'cancelled', 'timed_out', 'interrupted'}
ACTIVE = {'running', 'cancelling'}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.runner-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Settings:
    def __init__(self, runtime=None):
        self.runtime = Path(runtime or os.environ.get('LEON_QA_RUNNER_HOME') or PLATFORM_ROOT / '.runtime/qa-runner').resolve()
        self.runs = self.runtime / 'runs'
        self.config_file = self.runtime / 'projects.json'
        self.catalog_file = self.runtime / 'catalog.json'

    def configure(self, root):
        root = Path(root).resolve(strict=True)
        if 'module github.com/comes8/leon-qa-kit\n' not in (root / 'go.mod').read_text():
            raise ValueError('not a registered Leon QA Kit checkout')
        tools = {name: shutil.which(name) for name in ['bash', 'go', 'docker']}
        if not all(tools.values()):
            raise ValueError('bash, Go and Docker are required')
        context = os.environ.get('DOCKER_CONTEXT')
        endpoint = os.environ.get('DOCKER_HOST') if not context else None
        if not endpoint:
            command = [tools['docker'], 'context', 'inspect'] + ([context] if context else [])
            contexts = json.loads(subprocess.check_output(command, timeout=10, text=True))
            endpoint = contexts[0]['Endpoints']['docker']['Host']
        if not endpoint.startswith('unix:///'):
            raise ValueError('only a local Unix Docker endpoint can be registered')
        atomic_json(self.config_file, {'version': 1, 'project_key': PROJECT_KEY, 'root': str(root),
                                       'tools': tools, 'docker_endpoint': endpoint})

    def registration(self):
        data = json.loads(self.config_file.read_text())
        if data.get('version') != 1 or data.get('project_key') != PROJECT_KEY:
            raise ValueError('invalid local project registration')
        if not data.get('docker_endpoint', '').startswith('unix:///'):
            raise ValueError('run configure to pin a local Unix Docker endpoint')
        root = Path(data['root']).resolve(strict=True)
        if not root.is_dir() or not (root / 'qa.sh').is_file():
            raise ValueError('registered project is unavailable')
        data['root'] = str(root)
        for name in ['bash', 'go', 'docker']:
            path = Path(data['tools'][name])
            if not path.is_absolute() or not path.is_file():
                raise ValueError('registered tool is unavailable: ' + name)
        return data

    def job_root(self, run_id):
        import re
        if not re.fullmatch(r'job_[a-f0-9]{32}', run_id):
            raise ValueError('invalid managed run ID')
        result = self.runs / run_id
        if (self.runs.is_symlink() or self.runs.resolve() != self.runtime / 'runs'
                or result.is_symlink() or result.resolve().parent != self.runs):
            raise ValueError('managed run directory escaped runtime')
        return result

    def catalog(self):
        value = json.loads(self.catalog_file.read_text())
        reg = self.registration()
        if value.get('registered_root') != reg['root']:
            raise ValueError('registration changed; restart worker to refresh catalog')
        return value['catalog']
