from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError
from app.common.response import success_response
from app.core.database import get_db
from app.core.dependencies import get_current_user_id
from . import assets as A, design_service as S, design_schema as D
from .design_model import DesignTask, DesignArtifact, DesignJob

router = APIRouter()


def invalid_artifact(error):
    if isinstance(error, ValidationError):
        details = error.errors(include_input=False, include_url=False)
        message = '；'.join('.'.join(str(p) for p in item['loc']) + ': ' + item['msg'] for item in details[:8])
    else:
        message = str(error)
    return HTTPException(400, '业务产物校验失败：' + message[:1800])


@router.get('/options')
async def options(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    await A.ProjectService._check_project_member(project_id, user, db)
    models = (await db.scalars(select(S.AIModelConfigModel).where(
        S.AIModelConfigModel.created_by == user, S.AIModelConfigModel.enabled_flag == 1,
        S.AIModelConfigModel.is_active == 1, S.AIModelConfigModel.role.in_(['writer', 'reviewer'])))).all()
    return success_response({'stages': S.STAGES, 'output_schemas': {key: schema.model_json_schema() for key, schema in S.SCHEMAS.items()}, 'bundles': [A.bundle_summary(b) for b in await A.list_bundles(db, project_id, user)],
        'models': [{'id': m.id, 'name': m.name, 'role': m.role} for m in models], 'knowledge': await A.project_knowledge(db, project_id, user)})


@router.get('/tasks')
async def tasks(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    await A.ProjectService._check_project_member(project_id, user, db)
    rows = (await db.scalars(select(DesignTask).where(DesignTask.project_id == project_id,
        DesignTask.created_by == user, DesignTask.enabled_flag == 1).order_by(DesignTask.id.desc()).limit(100))).all()
    return success_response([{'id': r.id, 'title': r.title, 'input_revision': r.input_revision, 'busy_job_id': r.busy_job_id,
                              'updated_at': r.updation_date.isoformat()} for r in rows])


@router.post('/tasks')
async def create(body: D.CreateDesign, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.create_task(db, body, user)
    return success_response(await S.serialize_task(db, row))


@router.get('/tasks/{task_id}')
async def detail(task_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    return success_response(await S.serialize_task(db, await S.owned(db, task_id, user)))


@router.put('/tasks/{task_id}')
async def update(task_id: int, body: D.UpdateDesign, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, task_id, user, lock=True)
    await S.update_task(db, row, body, user)
    return success_response(await S.serialize_task(db, row))


@router.post('/tasks/{task_id}/preview')
async def preview(task_id: int, body: D.StageRequest, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, task_id, user)
    S.writable(row, body.expected_revision)
    snapshot = await S.prepare(db, row, body, user)
    return success_response({'snapshot': snapshot, 'input_hash': S.digest(snapshot), 'calls_model': False})


@router.post('/tasks/{task_id}/stages')
async def generate(task_id: int, body: D.StageRequest, background: BackgroundTasks,
                   db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, task_id, user, lock=True)
    job, created = await S.start_stage(db, row, body, user)
    if created:
        background.add_task(S.process_job, job.id)
    return success_response({'job': S.job_json(job), 'created': created})


@router.post('/tasks/{task_id}/confirm')
async def confirm(task_id: int, body: D.ConfirmArtifact, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, task_id, user, lock=True)
    await S.confirm_artifact(db, row, body, user)
    return success_response(await S.serialize_task(db, row))


@router.post('/tasks/{task_id}/revisions')
async def edit(task_id: int, body: D.EditArtifact, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, task_id, user, lock=True)
    try:
        await S.edit_artifact(db, row, body, user)
    except ValueError as error:
        raise invalid_artifact(error) from error
    return success_response(await S.serialize_task(db, row))


@router.post('/tasks/{task_id}/manual')
async def manual(task_id: int, body: D.ManualStage, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    row = await S.owned(db, task_id, user, lock=True)
    try:
        await S.manual_stage(db, row, body, user)
    except ValueError as error:
        raise invalid_artifact(error) from error
    return success_response(await S.serialize_task(db, row))


@router.get('/tasks/{task_id}/artifacts/{artifact_id}')
async def artifact(task_id: int, artifact_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    task = await S.owned(db, task_id, user)
    row = await db.scalar(select(DesignArtifact).where(DesignArtifact.task_id == task.id, DesignArtifact.id == artifact_id))
    if row is None:
        raise HTTPException(404, '产物版本不存在')
    heads = await S.head_artifacts(db, task)
    return success_response(S.artifact_json(row, task.heads.get(row.stage) == row.id and S.freshness(task, heads).get(row.stage, False)))


@router.get('/tasks/{task_id}/jobs/{job_id}')
async def job(task_id: int, job_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    await S.owned(db, task_id, user)
    row = await db.scalar(select(DesignJob).where(DesignJob.task_id == task_id, DesignJob.id == job_id, DesignJob.created_by == user))
    if row is None:
        raise HTTPException(404, '阶段任务不存在')
    return success_response(S.job_json(row, detail=True))


@router.get('/tasks/{task_id}/inputs/{revision}')
async def input_version(task_id: int, revision: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    task = await S.owned(db, task_id, user)
    if revision == task.input_revision:
        return success_response({'input_revision': revision, 'input': {k: getattr(task, k) for k in D.TaskInput.model_fields}, 'sources': task.source_snapshot})
    row = next((r for r in task.input_history if r['input_revision'] == revision), None)
    if row is None:
        raise HTTPException(404, '输入版本不存在')
    return success_response(row)


@router.get('/tasks/{task_id}/export')
async def export(task_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(get_current_user_id)):
    task = await S.owned(db, task_id, user)
    result = await S.serialize_task(db, task)
    rows = (await db.scalars(select(DesignArtifact).where(DesignArtifact.task_id == task.id).order_by(DesignArtifact.id))).all()
    heads = {s: next(r for r in rows if r.id == i) for s, i in task.heads.items()}
    fresh = S.freshness(task, heads)
    result['all_artifacts'] = [S.artifact_json(a, fresh=task.heads.get(a.stage) == a.id and fresh.get(a.stage, False)) for a in rows]
    result['all_inputs'] = task.input_history
    result['export_scope'] = '业务设计与版本追溯；不包含交易执行或测试通过证明'
    return JSONResponse(S.redact(result), headers={'Content-Disposition': f'attachment; filename="web3-design-{task.id}.json"'})
