"""Read/import business documents without invoking models or execution engines."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import success_response
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.api.v1.Ntesterc_module.Ntesterc_project.model import KnowledgeBaseModel, KnowledgeDocumentModel
from . import assets as A

router = APIRouter()


@router.get('/assets')
async def assets(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    return success_response([A.bundle_summary(row) for row in await A.list_bundles(db, project_id, user)])


@router.get('/assets/{bundle_id}')
async def bundle(bundle_id: int, project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await A.owned_bundle(db, project_id, user, bundle_id)
    return success_response({**A.bundle_summary(row),
        'skills': [{**s, 'integration': 'design_available' if s['key'] in A.SKILL_STAGES else 'library_only'} for s in row.snapshot['skills']],
        'prompts': [{**p, 'integration': 'design_available' if p.get('skill_key') in A.SKILL_STAGES else 'library_only'} for p in row.snapshot['prompts']]})


@router.get('/assets/{bundle_id}/file')
async def file(bundle_id: int, project_id: int, path: str, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await A.owned_bundle(db, project_id, user, bundle_id)
    return success_response(A.file_content(row, path))


@router.get('/source-preview')
async def source_preview(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row, snapshot, changes = await A.source_preview(db, project_id, user)
    return success_response({'baseline_id': row.id, 'manifest_sha256': snapshot['manifest_sha256'],
                             'version': snapshot['manifest_sha256'][:12], 'changes': changes,
                             'changed': any(changes.values()), 'counts': snapshot['counts']})


class SyncAssets(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int
    baseline_id: int
    manifest_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.post('/sync')
async def sync(body: SyncAssets, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row, snapshot, changes = await A.source_preview(db, body.project_id, user)
    if row.id != body.baseline_id or snapshot['manifest_sha256'] != body.manifest_sha256:
        raise HTTPException(409, '来源或导入版本已经变化，请重新检查差异')
    imported, created = await A.import_snapshot(db, body.project_id, user, snapshot)
    await db.commit()
    return success_response({**A.bundle_summary(imported), 'created': created})


@router.get('/knowledge')
async def knowledge(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    return success_response(await A.project_knowledge(db, project_id, user))


@router.get('/knowledge/{document_id}')
async def document(document_id: int, project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    await A.ProjectService._check_project_member(project_id, user, db)
    record = (await db.execute(select(KnowledgeDocumentModel).join(
        KnowledgeBaseModel, KnowledgeBaseModel.id == KnowledgeDocumentModel.knowledge_base_id,
    ).where(KnowledgeDocumentModel.id == document_id, KnowledgeBaseModel.project_id == project_id,
            KnowledgeBaseModel.enabled_flag == 1, KnowledgeDocumentModel.enabled_flag == 1))).scalar_one_or_none()
    if record is None:
        raise HTTPException(404, '知识文档不存在')
    content = record.content or ''
    return success_response({'title': record.title, 'content': content[:300_000], 'truncated': len(content) > 300_000})
