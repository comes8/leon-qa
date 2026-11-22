"""Authenticated fixed manual-fixture operations; no shell, URL or SQL input."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.Ntesterc_module.Ntesterc_project.service import ProjectService
from app.common.response import success_response
from app.core.database import async_session_factory, get_db
from .auth import actor
from .lab_model import LabOperation
from .lab_schema import LabRequest
from .lab_store import LabConflict, LabStore, public
from .settings import Settings
from .store import Store

router = APIRouter()


def store():
    return LabStore(async_session_factory)


@router.get('/state')
async def state(project_id: int, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await ProjectService._check_project_member(project_id, user, db)
    data = await store().listing(project_id, user)
    data['worker'] = await Store(async_session_factory).health()
    return success_response(data)


@router.post('/operations')
async def submit(body: LabRequest, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    await ProjectService._check_project_member(body.project_id, user, db)
    try:
        registration = Settings().registration() if body.action == 'start' else {}
    except (ValueError, OSError) as exc:
        raise HTTPException(503, '请先登记本地工具包并启动执行器') from exc
    if (await Store(async_session_factory).health())['status'] == 'blocked':
        raise HTTPException(503, '本地执行器异常，需检查归属清理记录后重新启动')
    try:
        op, duplicate = await store().submit(body, user, registration)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except LabConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return JSONResponse(status_code=200 if duplicate else 202,
                        content=jsonable_encoder(success_response({'operation': public(op), 'duplicate': duplicate})))


@router.get('/operations/{operation_id}')
async def operation(operation_id: str, db: AsyncSession = Depends(get_db), user: int = Depends(actor)):
    op = await store().get(LabOperation, operation_id)
    if not op or op['user_id'] != user:
        raise HTTPException(404, '操作记录不存在')
    await ProjectService._check_project_member(op['project_id'], user, db)
    return success_response(public(op))
