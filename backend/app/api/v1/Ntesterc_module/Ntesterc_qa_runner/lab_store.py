"""Durable, idempotent manual operations; never store business balances in platform tables."""
import hashlib
import json
from datetime import datetime
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .lab_model import LabDataset, LabEnvironment, LabOperation
from .model import now
from .store import plain


class LabConflict(ValueError):
    pass


def public(row):
    hidden = {'registration', 'launch_token', 'process_created', 'fingerprint', 'active_slot', 'capacity_slot', 'busy_slot'}
    return {k: v.isoformat(timespec='milliseconds') + 'Z' if isinstance(v, datetime) else
            str(v) if k in {'project_id', 'user_id', 'created_by', 'updated_by'} and v is not None else v
            for k, v in row.items() if k not in hidden}


class LabStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def get(self, model, identity):
        async with self.sessions() as db:
            row = await db.get(model, identity)
            return plain(row) if row else None

    async def listing(self, project, user):
        async with self.sessions() as db:
            envs = (await db.scalars(select(LabEnvironment).where(LabEnvironment.project_id == project,
                LabEnvironment.user_id == user).order_by(LabEnvironment.creation_date.desc()).limit(40))).all()
            ids = [e.id for e in envs]
            data = (await db.scalars(select(LabDataset).where(LabDataset.environment_id.in_(ids)).order_by(LabDataset.creation_date))).all() if ids else []
            ops = (await db.scalars(select(LabOperation).where(LabOperation.project_id == project,
                LabOperation.user_id == user).order_by(LabOperation.creation_date.desc()).limit(100))).all()
            return {'environments': [public(plain(e)) for e in envs], 'datasets': [public(plain(d)) for d in data],
                    'operations': [public(plain(o)) for o in ops], 'limits': {'manual_environments': 2, 'per_project_user': 1}}

    async def submit(self, body, user, registration):
        inputs = body.model_dump(exclude_none=True)
        fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        for attempt in range(4):
            async with self.sessions() as db:
                old = await db.scalar(select(LabOperation).where(LabOperation.project_id == body.project_id,
                    LabOperation.user_id == user, LabOperation.request_key == body.request_key))
                if old:
                    if old.fingerprint != fingerprint:
                        raise LabConflict('原请求标识已用于不同参数，请刷新确认原操作')
                    return plain(old), True
                audit = {'created_by': user, 'updated_by': user, 'enabled_flag': 1}
                dataset = None
                if body.action == 'start':
                    active = (await db.scalars(select(LabEnvironment).where(LabEnvironment.active_slot.is_not(None)))).all()
                    owner_slot = f'{body.project_id}:{user}'
                    if any(e.active_slot == owner_slot for e in active):
                        raise LabConflict('当前项目已有手工环境，请先查看或停止该环境')
                    free = sorted({0, 1} - {e.capacity_slot for e in active})
                    if not free:
                        raise LabConflict('本机最多同时保留两套手工环境，请先停止空闲环境')
                    identity = uuid4().hex
                    env = LabEnvironment(id=identity, project_id=body.project_id, user_id=user,
                        active_slot=owner_slot, capacity_slot=free[0], status='queued', session_id='env_' + identity,
                        launch_token=uuid4().hex, registration=registration, cleanup_status='not_started', **audit)
                    db.add(env)
                else:
                    env = await db.get(LabEnvironment, body.environment_id)
                    if not env or env.project_id != body.project_id or env.user_id != user:
                        raise LookupError('环境不存在')
                    if await db.scalar(select(LabOperation.id).where(LabOperation.busy_slot == env.id)):
                        raise LabConflict('环境有操作尚未结束，请等待原操作结果')
                    if body.action != 'stop' and env.status != 'running':
                        raise LabConflict('环境未就绪，请先启动手工环境')
                    if body.action == 'create':
                        dataset = LabDataset(id=uuid4().hex, environment_id=env.id, name=body.name,
                            funding=body.funding, spot=body.spot, status='creating', revision=1, generation=0, history=[], **audit)
                        db.add(dataset)
                    elif body.dataset_id:
                        dataset = await db.get(LabDataset, body.dataset_id)
                        if not dataset or dataset.environment_id != env.id:
                            raise LookupError('数据集不存在')
                        if dataset.revision != body.expected_revision:
                            raise LabConflict('数据集版本已变化，请刷新后操作')
                        allowed = {'inspect': {'ready'}, 'delete': {'ready'}, 'rebuild': {'ready', 'deleted', 'error'},
                                   'transfer': {'ready'}, 'query': {'ready'}, 'verify': {'ready'}}[body.action]
                        if dataset.status not in allowed:
                            raise LabConflict('当前数据集状态不允许此操作')
                        dataset.status = {'inspect': 'inspecting', 'delete': 'deleting', 'rebuild': 'rebuilding',
                                          'transfer': 'debugging', 'query': 'debugging', 'verify': 'debugging'}[body.action]
                        dataset.revision += 1
                        dataset.updation_date = now()
                    elif body.action == 'stop':
                        if env.status not in {'running', 'error', 'stopped', 'interrupted'}:
                            raise LabConflict('环境仍在启动或停止，请等待操作完成')
                        env.status = 'stopping'
                operation = LabOperation(id=uuid4().hex, project_id=body.project_id, user_id=user,
                    environment_id=env.id, dataset_id=dataset.id if dataset else None, busy_slot=env.id,
                    action=body.action, request_key=body.request_key, fingerprint=fingerprint,
                    inputs=inputs, status='queued', **audit)
                db.add(operation)
                try:
                    await db.commit()
                    return plain(operation), False
                except IntegrityError:
                    await db.rollback()
                    if attempt == 3:
                        raise LabConflict('环境正被其他请求操作，请刷新确认后重试')

    async def claim(self):
        async with self.sessions() as db:
            row = await db.scalar(select(LabOperation).where(LabOperation.status == 'queued').order_by(
                LabOperation.creation_date, LabOperation.id).limit(1))
            if not row:
                return None
            result = await db.execute(update(LabOperation).where(LabOperation.id == row.id,
                LabOperation.status == 'queued').values(status='running', updation_date=now()))
            if result.rowcount != 1:
                await db.rollback()
                return None
            await db.commit(); await db.refresh(row)
            return plain(row)

    async def patch(self, model, identity, values):
        async with self.sessions() as db:
            await db.execute(update(model).where(model.id == identity).values(**values, updation_date=now()))
            await db.commit()

    async def finish(self, op, result=None, error=None):
        await self.patch(LabOperation, op['id'], {'status': 'error' if error else 'completed', 'result': result,
                                                'error_message': error, 'busy_slot': None})

    async def environments(self, active_only=True):
        async with self.sessions() as db:
            query = select(LabEnvironment)
            if active_only:
                query = query.where(LabEnvironment.active_slot.is_not(None), LabEnvironment.status != 'queued')
            return [plain(r) for r in (await db.scalars(query)).all()]

    async def retire(self, env_id, state, clean, message=None):
        async with self.sessions() as db:
            env = await db.get(LabEnvironment, env_id)
            if env:
                env.status = state; env.cleanup_status = 'clean' if clean else 'failed'; env.error_message = message
                env.updation_date = now()
                if clean:
                    env.active_slot = None; env.capacity_slot = None
            await db.execute(update(LabDataset).where(LabDataset.environment_id == env_id,
                LabDataset.status != 'deleted').values(status='unavailable', updation_date=now(), revision=LabDataset.revision + 1))
            await db.commit()

    async def recover_operations(self):
        async with self.sessions() as db:
            rows = (await db.scalars(select(LabOperation).where(LabOperation.status.in_(['queued', 'running'])))).all()
            for row in rows:
                env = await db.get(LabEnvironment, row.environment_id)
                if row.status == 'running' or not env or env.status != 'queued' and env.status != 'running':
                    row.status = 'interrupted'; row.busy_slot = None; row.updation_date = now()
                    row.error_message = '执行器重启，原操作中断；未自动重放，历史快照保留'
            await db.commit()
