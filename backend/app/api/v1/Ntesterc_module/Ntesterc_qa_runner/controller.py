"""Authenticated task APIs; no request accepts commands, roots, env or URLs."""
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.response import success_response
from app.core.database import async_session_factory, get_db
from app.api.v1.Ntesterc_module.Ntesterc_project.service import ProjectService
from .protocol import artifact_path
from .schema import CreateJob
from .settings import Settings, TERMINAL
from .store import RequestConflict, Store, public
from .auth import actor

router = APIRouter()


def store():
    return Store(async_session_factory)


async def owned(job_id, user_id, db):
    row = await store().get(job_id)
    if not row or row['user_id'] != user_id:
        raise HTTPException(404, '任务不存在')
    await ProjectService._check_project_member(row['project_id'], user_id, db)
    return row


@router.get('/catalog')
async def catalog(user: int = Depends(actor)):
    settings = Settings()
    try:
        data = settings.catalog()
        health = await store().health()
        return success_response({'project_key': 'leon-qa-kit', 'catalog': data, 'worker': health})
    except (OSError, ValueError):
        return success_response({'project_key': 'leon-qa-kit', 'catalog': None,
                                 'worker': {'status': 'not_configured'}})


@router.get('/diagnostics')
async def diagnostics(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await ProjectService._check_project_member(project_id, user, db)
    from .health import for_project
    return success_response(await for_project(project_id, user))


@router.post('/jobs')
async def submit(body: CreateJob, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await ProjectService._check_project_member(body.project_id, user, db)
    settings = Settings()
    try:
        reg = settings.registration()
        settings.catalog()
    except (OSError, ValueError) as exc:
        raise HTTPException(503, '本地项目未就绪，请先配置并启动执行器') from exc
    if (await store().health())['status'] == 'blocked':
        raise HTTPException(503, '本地执行器需要处理上次异常，请检查执行器状态')
    try:
        job, duplicate = await store().submit(body, user, reg, settings)
    except RequestConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(503, '本地运行目录异常，请检查执行器配置') from exc
    return JSONResponse(status_code=200 if duplicate else 202,
                        content=jsonable_encoder(success_response({'job': public(job), 'duplicate': duplicate})))


@router.get('/jobs')
async def jobs(project_id: int, limit: int = Query(50, ge=1, le=100),
               db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await ProjectService._check_project_member(project_id, user, db)
    return success_response({'items': [public(r) for r in await store().list(project_id, user, limit)]})


@router.get('/jobs/{job_id}')
async def get(job_id: str, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    return success_response(public(await owned(job_id, user, db)))


@router.post('/jobs/{job_id}/cancel')
async def cancel(job_id: str, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await owned(job_id, user, db)
    job = await store().cancel(job_id)
    return JSONResponse(status_code=200 if job['status'] in TERMINAL else 202,
                        content=jsonable_encoder(success_response(public(job))))


@router.get('/jobs/{job_id}/events')
async def events(job_id: str, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                 db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await owned(job_id, user, db)
    rows = await store().events(job_id, after, limit)
    return success_response({'items': rows, 'next_after': rows[-1]['seq'] if rows else after})


@router.get('/jobs/{job_id}/logs')
async def logs(job_id: str, stream: Literal['stderr', 'stdout', 'supervisor'] = 'stderr',
               offset: int = Query(0, ge=0), limit: int = Query(65536, ge=4, le=262144),
               db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    job = await owned(job_id, user, db)
    folder = Settings().job_root(job['run_id'])
    filename = {'stderr': 'stderr.log', 'stdout': 'stdout.json', 'supervisor': 'supervisor.log'}[stream]
    path = folder / filename
    data, size = b'', 0
    if path.exists():
        if path.is_symlink():
            raise HTTPException(409, '日志路径异常')
        with path.open('rb') as source:
            size = path.stat().st_size
            if offset > size:
                raise HTTPException(416, '日志偏移超出文件范围')
            source.seek(offset)
            data = source.read(limit)
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            if exc.reason == 'unexpected end of data' and exc.start:
                data = data[:exc.start]
            text = data.decode('utf-8', errors='replace')
    else:
        text = ''
    return success_response({'stream': stream, 'offset': offset, 'next_offset': offset + len(data),
                             'size_bytes': size, 'text': text,
                             'complete': job['status'] in TERMINAL and offset + len(data) >= size})


@router.get('/jobs/{job_id}/report')
async def report(job_id: str, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    job = await owned(job_id, user, db)
    if not job['result']:
        raise HTTPException(409, '尚无可导入的完整报告，请查看任务状态与日志')
    return success_response(job['result'])


@router.get('/jobs/{job_id}/artifacts/{relative:path}')
async def artifact(job_id: str, relative: str, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    job = await owned(job_id, user, db)
    if not job['result'] or relative not in job['result']['artifacts']:
        raise HTTPException(404, '产物不存在')
    try:
        path = artifact_path(job['output_dir'], relative)
    except (OSError, ValueError) as exc:
        raise HTTPException(404, '产物不可访问') from exc
    return FileResponse(path, filename=path.name, media_type='application/octet-stream')


from .lab_controller import router as lab_router
router.include_router(lab_router, prefix='/lab', tags=['本地业务状态准备'])
