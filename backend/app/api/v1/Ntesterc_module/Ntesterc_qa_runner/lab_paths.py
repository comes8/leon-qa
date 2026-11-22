import hashlib
from pathlib import Path
import re


class LabPaths:
    def __init__(self, settings):
        self.root = settings.runtime / 'manual'

    def job_root(self, session_id):
        if not re.fullmatch(r'env_[a-f0-9]{32}', session_id):
            raise ValueError('invalid manual environment identity')
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ValueError('manual environment root cannot be a symlink')
        return child(self.root, session_id)


def child(root, *parts):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('private directory cannot be a symlink')
    target = root.joinpath(*parts)
    for path in [target, *target.parents]:
        if path == root.parent:
            break
        if path.is_symlink():
            raise ValueError('private path cannot follow symlinks')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('private path escaped environment')
    return target


def source_digest(root):
    root = Path(root)
    paths = [root / 'go.mod', root / 'go.sum'] + [p for p in root.rglob('*.go')
        if not any(part in {'.git', '.runtime', 'artifacts'} for part in p.relative_to(root).parts)]
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise ValueError('source symlinks are not supported')
        digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()
