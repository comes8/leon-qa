from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from app.common.response import success_response
from . import service as S
from .mock import router as mock_router
from .workspace_controller import router as workspace_router
from .design_controller import router as design_router
from .model import Web3WorkflowModel
from .schema import ApproveWorkflow, CreateWorkflow, ExecuteWorkflow, UpdateAnalysis, UpdateDraft

router = APIRouter()
router.include_router(mock_router, prefix='/mock')
router.include_router(workspace_router, prefix='/workspace')
router.include_router(design_router, prefix='/design')


@router.get('/options')
async def get_options(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    return success_response(await S.options(db, project_id, user))


@router.get('/workflows')
async def workflows(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    await S.ProjectService._check_project_member(project_id, user, db)
    rows = (await db.scalars(select(Web3WorkflowModel).where(
        Web3WorkflowModel.project_id == project_id, Web3WorkflowModel.created_by == user,
        Web3WorkflowModel.enabled_flag == 1,
    ).order_by(Web3WorkflowModel.id.desc()).limit(50))).all()
    return success_response([{'id': row.id, 'title': row.title, 'status': row.status, 'updated_at': row.updation_date.isoformat()} for row in rows])


@router.post('/workflows')
async def create(body: CreateWorkflow, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.create_workflow(db, body, user)
    await S.claim(db, row, {'created'}, 'analyzing')
    tasks.add_task(S.process, row.id, 'analysis', user)
    return success_response({'id': row.id, 'status': 'analyzing'})


@router.get('/workflows/{run_id}')
async def get_workflow(run_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    return success_response(S.serialize(await S.owned(db, run_id, user)))


@router.post('/workflows/{run_id}/actions/{action}')
async def stage(run_id: int, action: str, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, run_id, user)
    if action == 'analyze':
        if row.publication:
            raise HTTPException(409, '已发布任务请新建需求分析，保留当前回归记录')
        await S.claim(db, row, {'created', 'error', 'analysis_ready'}, 'analyzing')
        stage_name = 'analysis'
    elif action in {'generate', 'revise'}:
        if not row.analysis or row.publication:
            raise HTTPException(409, '请先完成需求分析')
        if action == 'revise' and (not row.draft or not row.review):
            raise HTTPException(409, '请先完成用例生成与评审')
        await S.claim(db, row, {'analysis_ready', 'review_ready', 'error'}, 'generating')
        stage_name = action
    elif action == 'review':
        if not row.draft or row.publication:
            raise HTTPException(409, '请先生成用例草稿')
        await S.claim(db, row, {'review_ready', 'draft_edited', 'error'}, 'generating')
        stage_name = 'review'
    else:
        raise HTTPException(404, '操作不存在')
    tasks.add_task(S.process, run_id, stage_name, user)
    return success_response({'id': run_id})


@router.put('/workflows/{run_id}/draft')
async def edit_draft(run_id: int, body: UpdateDraft, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, run_id, user)
    await S.claim(db, row, {'review_ready', 'draft_edited'}, 'draft_edited', body.revision)
    S.preserve_version(row, 'edit_draft')
    row.draft = body.draft.model_dump()
    row.review = None
    row.revision += 1
    await db.commit()
    return success_response(S.serialize(row))


@router.put('/workflows/{run_id}/analysis')
async def edit_analysis(run_id: int, body: UpdateAnalysis, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, run_id, user)
    if row.publication:
        raise HTTPException(409, '已发布任务请新建需求版本，保留当前回归证据')
    sources = {source['source_id']: source['content'] for source in (row.citations or [])}
    ids = [point.id for point in body.analysis.coverage]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, '覆盖编号不可重复')
    for point in body.analysis.coverage:
        if not set(point.source_ids).issubset(sources):
            raise HTTPException(400, '覆盖项引用了不存在的文档')
        text = '\n'.join(sources[key] for key in point.source_ids)
        if any(rule not in text for rule in point.rule_ids):
            raise HTTPException(400, '覆盖项规则编号与来源不符')
    await S.claim(db, row, {'analysis_ready', 'review_ready', 'draft_edited', 'error'}, 'analysis_ready', body.revision)
    S.preserve_version(row, 'confirm_analysis')
    row.analysis = {**body.analysis.model_dump(), '_versions': row.analysis.get('_versions', []),
                    '_review': {'by': user, 'at': S.now(), 'note': body.note.strip()}}
    row.draft, row.review = None, None
    row.revision += 1
    await db.commit()
    return success_response(S.serialize(row))


@router.post('/workflows/{run_id}/approve')
async def approve(run_id: int, body: ApproveWorkflow, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, run_id, user)
    await S.approve(db, row, body)
    return success_response(S.serialize(row))


@router.post('/workflows/{run_id}/execute')
async def execute(run_id: int, body: ExecuteWorkflow, tasks: BackgroundTasks, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, run_id, user)
    if not body.confirm_test_environment:
        raise HTTPException(400, '请先确认所选测试环境')
    if not row.approval or not row.publication:
        raise HTTPException(400, '请先评审并发布用例集')
    await S.verify_targets(db, row)
    await S.claim(db, row, {'suite_ready', 'passed', 'failed', 'error'}, 'executing', body.revision)
    tasks.add_task(S.process, run_id, 'execute', user)
    return success_response({'id': run_id, 'status': 'executing'})


@router.get('/workflows/{run_id}/export')
async def export(run_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, run_id, user)
    return JSONResponse(S.redact(S.serialize(row)), headers={'Content-Disposition': f'attachment; filename="web3-workflow-{run_id}.json"'})
