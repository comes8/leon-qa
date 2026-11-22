"""Versioned, document-only business assets. Importing never runs a Skill."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re

from fastapi import HTTPException
from sqlalchemy import BigInteger, Column, JSON, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError

from app.core.db_base import Base
from app.core.database import engine
from app.api.v1.Ntesterc_module.Ntesterc_project.model import KnowledgeBaseModel, KnowledgeDocumentModel
from app.api.v1.Ntesterc_module.Ntesterc_project.service import ProjectService


SOURCE_KEY = 'web3-cex-business-skills'
# Bundled document pack; an explicit environment override may select another pack.
import os
SOURCE_ROOT = Path(os.environ.get('LEON_QA_BUSINESS_ASSETS') or
                   Path(__file__).resolve().parents[6] / 'resources/web3-cex-business-skills')
SKILL_STAGES = {
    'cex-requirement-review': ('需求分析', 'P01', 'P02'),
    'cex-business-modeling': ('业务建模', 'P03', 'P04'),
    'cex-testpoint-design': ('测试点设计', 'P05', 'P06'),
    'cex-testpoint-review': ('测试点评审', 'P07'),
    'cex-testcase-design-review': ('用例与评审', 'P08', 'P09'),
    'cex-spot-matching': ('现货专项', 'P10'),
    'cex-futures-risk': ('合约专项', 'P11'),
    'cex-funds-reconciliation': ('资金专项', 'P12'),
    'cex-change-regression': ('变更回归', 'P13', 'P14'),
}


class BusinessAssetBundle(Base):
    __tablename__ = 'web3_business_asset_bundles'
    __table_args__ = (
        UniqueConstraint('project_id', 'created_by', 'source_key', 'manifest_sha256', name='uq_web3_business_bundle'),
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_general_ci'},
    )
    project_id = Column(BigInteger, nullable=False, index=True)
    source_key = Column(String(100), nullable=False)
    source_root = Column(String(1000), nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    snapshot = Column(JSON, nullable=False)


async def ensure_assets_schema():
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: BusinessAssetBundle.__table__.create(conn, checkfirst=True))


def _read(root: Path, path: Path) -> dict:
    if root.is_symlink() or path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
        raise ValueError('业务资产不允许使用符号链接')
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('业务资产文件超出登记目录')
    raw = path.read_bytes()
    if len(raw) > 300_000:
        raise ValueError('单份业务资产超过300KB')
    return {'path': path.relative_to(root).as_posix(), 'sha256': sha256(raw).hexdigest(),
            'content': raw.decode('utf-8'), 'bytes': len(raw)}


def _title(content: str) -> str:
    return next((line.lstrip('# ').strip() for line in content.splitlines() if line.startswith('# ')), '')


def scan_bundle(root: Path) -> dict:
    """Read only the documented pack layout, excluding evals and executables."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('登记的业务资料目录不存在或为符号链接')
    paths = [root / 'README.md']
    skills, prompts = [], []
    for entry in sorted(root.glob('*/SKILL.md')):
        record = _read(root, entry)
        name = entry.parent.name
        match = re.search(r'^name:\s*[\"\']?([^\n\"\']+)', record['content'], re.M)
        if match and match.group(1).strip() != name:
            raise ValueError('Skill名称与目录不一致')
        description = re.search(r'^description:\s*(.+)$', record['content'], re.M)
        stage, *prompt_ids = SKILL_STAGES.get(name, ('业务方法',))
        refs = sorted((entry.parent / 'references').glob('*.md'))
        paths.extend([entry, *refs])
        agent = entry.parent / 'agents' / 'openai.yaml'
        if agent.exists():
            paths.append(agent)
        skills.append({'key': name, 'title': _title(record['content']),
                       'description': description.group(1).strip().strip('"\'') if description else '',
                       'stage': stage, 'prompt_ids': prompt_ids, 'path': record['path'],
                       'references': [p.relative_to(root).as_posix() for p in refs],
                       'execution_mode': 'document_method', 'integration': 'imported_not_bound'})
    for path in sorted((root / 'prompts').glob('P[0-9][0-9]-*.md')):
        record = _read(root, path)
        key = path.name.split('-')[0]
        related = next((s for s in skills if key in s['prompt_ids']), None)
        prompts.append({'key': key, 'title': _title(record['content']), 'path': record['path'],
                        'stage': related['stage'] if related else '任务模板',
                        'skill_key': related['key'] if related else None,
                        'variables': list(dict.fromkeys(re.findall(r'\{\{([^{}]+)\}\}', record['content']))),
                        'integration': 'imported_not_bound'})
        paths.append(path)
    if not skills or not prompts or len(paths) > 256:
        raise ValueError('资料包缺少Skill/Prompt或文件过多')
    files = {p.relative_to(root).as_posix(): _read(root, p) for p in sorted(set(paths))}
    if sum(p['bytes'] for p in files.values()) > 4_000_000:
        raise ValueError('业务资料包超过4MB')
    for entry in files.values():
        for target in re.findall(r'\]\(([^)]+)\)', entry['content']):
            target = target.split('#')[0]
            if not target or '://' in target:
                continue
            resolved = (root / entry['path']).parent / target
            if resolved.is_symlink() or not resolved.resolve().is_relative_to(root.resolve()):
                raise ValueError('业务资产包含越界引用')
            relative = resolved.resolve().relative_to(root.resolve()).as_posix()
            # README references evaluations deliberately retained only in the original pack.
            if relative.startswith('evals/'):
                continue
            if relative not in files:
                raise ValueError('业务资产缺少本地引用: ' + relative)
    manifest = {path: entry['sha256'] for path, entry in files.items()}
    digest = sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'source_key': SOURCE_KEY, 'manifest_sha256': digest, 'skills': skills, 'prompts': prompts,
            'files': files, 'counts': {'skills': len(skills), 'prompts': len(prompts),
                                      'references': sum('/references/' in p for p in files), 'files': len(files)}}


def bundle_summary(row):
    return {'id': row.id, 'source_key': row.source_key, 'source_root': row.source_root,
            'version': row.manifest_sha256[:12], 'manifest_sha256': row.manifest_sha256,
            'imported_at': row.creation_date.isoformat() if row.creation_date else None,
            'counts': row.snapshot['counts'], 'integration': 'design_available',
            'design_bindings': {s['key']: [p for p in SKILL_STAGES.get(s['key'], ('',))[1:]
                                         if any(t['key'] == p for t in row.snapshot['prompts'])]
                                for s in row.snapshot['skills'] if s['key'] in SKILL_STAGES}}


async def list_bundles(db, project_id, user_id):
    await ProjectService._check_project_member(project_id, user_id, db)
    return (await db.scalars(select(BusinessAssetBundle).where(
        BusinessAssetBundle.project_id == project_id, BusinessAssetBundle.created_by == user_id,
        BusinessAssetBundle.enabled_flag == 1,
    ).order_by(BusinessAssetBundle.id.desc()))).all()


async def owned_bundle(db, project_id, user_id, bundle_id):
    await ProjectService._check_project_member(project_id, user_id, db)
    row = await db.scalar(select(BusinessAssetBundle).where(
        BusinessAssetBundle.id == bundle_id, BusinessAssetBundle.project_id == project_id,
        BusinessAssetBundle.created_by == user_id, BusinessAssetBundle.enabled_flag == 1,
    ))
    if row is None:
        raise HTTPException(404, '业务资料版本不存在')
    return row


def file_content(row, relative):
    # Exact immutable snapshot lookup, never use browser input as a disk path.
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != relative:
        raise HTTPException(400, '资料路径无效')
    entry = row.snapshot['files'].get(relative)
    if entry is None:
        raise HTTPException(404, '版本中不存在该文件')
    return entry


def compare_snapshot(before, after):
    old, new = before['files'], after['files']
    return {'added': sorted(set(new) - set(old)), 'removed': sorted(set(old) - set(new)),
            'modified': sorted(p for p in set(new) & set(old) if new[p]['sha256'] != old[p]['sha256'])}


async def import_snapshot(db, project_id, user_id, snapshot, source_root=SOURCE_ROOT):
    await ProjectService._check_project_permission(project_id, user_id, ['owner', 'admin', 'developer'], db)
    existing = await db.scalar(select(BusinessAssetBundle).where(
        BusinessAssetBundle.project_id == project_id, BusinessAssetBundle.created_by == user_id,
        BusinessAssetBundle.source_key == SOURCE_KEY,
        BusinessAssetBundle.manifest_sha256 == snapshot['manifest_sha256'], BusinessAssetBundle.enabled_flag == 1,
    ))
    if existing:
        return existing, False
    row = BusinessAssetBundle(project_id=project_id, source_key=SOURCE_KEY, source_root=str(source_root),
                              manifest_sha256=snapshot['manifest_sha256'], snapshot=snapshot,
                              created_by=user_id, updated_by=user_id)
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        existing = await db.scalar(select(BusinessAssetBundle).where(
            BusinessAssetBundle.project_id == project_id, BusinessAssetBundle.created_by == user_id,
            BusinessAssetBundle.source_key == SOURCE_KEY,
            BusinessAssetBundle.manifest_sha256 == snapshot['manifest_sha256'], BusinessAssetBundle.enabled_flag == 1,
        ))
        if existing is None:
            raise
        return existing, False
    return row, True


async def source_preview(db, project_id, user_id):
    await ProjectService._check_project_permission(project_id, user_id, ['owner', 'admin', 'developer'], db)
    rows = await list_bundles(db, project_id, user_id)
    if not rows or rows[0].source_root != str(SOURCE_ROOT):
        raise HTTPException(404, '此项目尚未登记本地业务资料来源')
    try:
        snapshot = scan_bundle(SOURCE_ROOT)
    except (OSError, ValueError, UnicodeError) as exc:
        raise HTTPException(409, '无法读取业务资料：' + str(exc)) from exc
    return rows[0], snapshot, compare_snapshot(rows[0].snapshot, snapshot)


async def project_knowledge(db, project_id, user_id):
    await ProjectService._check_project_member(project_id, user_id, db)
    bases = (await db.scalars(select(KnowledgeBaseModel).where(
        KnowledgeBaseModel.project_id == project_id, KnowledgeBaseModel.enabled_flag == 1,
    ).order_by(KnowledgeBaseModel.id))).all()
    if not bases:
        return []
    docs = (await db.scalars(select(KnowledgeDocumentModel).where(
        KnowledgeDocumentModel.knowledge_base_id.in_([b.id for b in bases]),
        KnowledgeDocumentModel.enabled_flag == 1,
    ).order_by(KnowledgeDocumentModel.id))).all()
    return [{'id': b.id, 'name': b.name, 'description': b.description, 'is_active': bool(b.is_active),
             'documents': [{'id': d.id, 'title': d.title, 'status': d.status,
                            'sha256': sha256((d.content or '').encode()).hexdigest(),
                            'characters': len(d.content or '')} for d in docs if d.knowledge_base_id == b.id]} for b in bases]
