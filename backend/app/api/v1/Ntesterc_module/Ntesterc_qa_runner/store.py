"""Short transactions and revision-checked state changes, shared by API/worker."""
from datetime import datetime
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, update, or_
from sqlalchemy.exc import IntegrityError
from .model import RunnerEvent, RunnerJob, RunnerWorker, now
from .settings import TERMINAL


class RequestConflict(ValueError):
    pass


def plain(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def public(job):
    hidden = {'launch_token', 'process_created', 'request_fingerprint', 'toolkit_root'}
    out = {k: v for k, v in job.items() if k not in hidden}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat(timespec='milliseconds') + 'Z'
        elif k in {'project_id', 'user_id', 'created_by', 'updated_by'} and v is not None:
            out[k] = str(v)
    return out


class Store:
    def __init__(self, sessions):
        self.sessions = sessions

    async def get(self, job_id):
        async with self.sessions() as db:
            row = await db.get(RunnerJob, job_id)
            return plain(row) if row else None

    async def submit(self, body, user_id, registration, settings):
        inputs = body.model_dump()
        fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        async with self.sessions() as db:
            old = await db.scalar(select(RunnerJob).where(RunnerJob.project_id == body.project_id,
                RunnerJob.user_id == user_id, RunnerJob.request_key == body.request_key))
            if old:
                if old.request_fingerprint != fingerprint:
                    raise RequestConflict('same request_key with different inputs')
                return plain(old), True
            identity = uuid4().hex
            row = RunnerJob(id=identity, project_id=body.project_id, user_id=user_id,
                request_key=body.request_key, request_fingerprint=fingerprint, project_key=body.project_key,
                toolkit_root=registration['root'], suite_id=body.suite_id, suite_version='1.0.0',
                run_kind=body.run_kind, run_id='job_' + identity,
                output_dir=str(settings.job_root('job_' + identity) / 'report'), timeout_seconds=body.timeout_seconds,
                status='queued', revision=1, launch_token=uuid4().hex, cleanup_status='not_started',
                created_by=user_id, updated_by=user_id, enabled_flag=1)
            db.add(row)
            db.add(RunnerEvent(job_id=identity, seq=1, code='queued', message='任务已持久化，等待本地执行器', created_by=user_id))
            try:
                await db.commit()
                return plain(row), False
            except IntegrityError:
                await db.rollback()
        # A competing HTTP request may have inserted the same idempotency key.
        async with self.sessions() as db:
            old = await db.scalar(select(RunnerJob).where(RunnerJob.project_id == body.project_id,
                RunnerJob.user_id == user_id, RunnerJob.request_key == body.request_key))
            if not old or old.request_fingerprint != fingerprint:
                raise RequestConflict('same request_key with different inputs')
            return plain(old), True

    async def change(self, job_id, states, values, code, message):
        for _ in range(5):
            async with self.sessions() as db:
                row = await db.get(RunnerJob, job_id)
                if not row or row.status not in states:
                    return None
                revision = row.revision
                changes = dict(values, revision=revision + 1, updation_date=now())
                result = await db.execute(update(RunnerJob).where(RunnerJob.id == job_id,
                    RunnerJob.status.in_(states), RunnerJob.revision == revision).values(**changes))
                if result.rowcount != 1:
                    await db.rollback()
                    continue
                db.add(RunnerEvent(job_id=job_id, seq=revision + 1, code=code, message=message,
                                   level='error' if code.endswith('error') else 'info', created_by=row.user_id))
                await db.commit()
                await db.refresh(row)
                return plain(row)
        raise RuntimeError('task revision contention; retry the operation')

    async def cancel(self, job_id):
        job = await self.get(job_id)
        if not job or job['status'] in TERMINAL or job['status'] == 'cancelling':
            return job
        if job['status'] == 'queued':
            changed = await self.change(job_id, {'queued'}, {'status': 'cancelled',
                'cancel_requested_at': now(), 'finished_at': now(), 'cleanup_status': 'not_required'},
                'cancelled', '排队任务已取消，未启动测试进程')
            if changed:
                return changed
        changed = await self.change(job_id, {'running'}, {'status': 'cancelling', 'cancel_requested_at': now()},
                                    'cancel_requested', '已请求取消，执行器正在结束本次进程并清理资源')
        return changed or await self.get(job_id)

    async def claim(self, worker_id):
        async with self.sessions() as db:
            identity = await db.scalar(select(RunnerJob.id).where(RunnerJob.status == 'queued').order_by(
                RunnerJob.creation_date, RunnerJob.id).limit(1))
        if not identity:
            return None
        return await self.change(identity, {'queued'}, {'status': 'running', 'worker_id': worker_id,
            'started_at': now(), 'cleanup_status': 'pending'}, 'started', '本地执行器已领取任务')

    async def recoverable(self):
        async with self.sessions() as db:
            rows = (await db.scalars(select(RunnerJob).where(or_(RunnerJob.status.in_(['running', 'cancelling']),
                RunnerJob.cleanup_status == 'failed')).order_by(RunnerJob.creation_date))).all()
            return [plain(r) for r in rows]

    async def list(self, project_id, user_id, limit=50):
        async with self.sessions() as db:
            rows = (await db.scalars(select(RunnerJob).where(RunnerJob.project_id == project_id,
                RunnerJob.user_id == user_id).order_by(RunnerJob.creation_date.desc(), RunnerJob.id.desc()).limit(limit))).all()
            return [plain(r) for r in rows]

    async def events(self, job_id, after=0, limit=100):
        async with self.sessions() as db:
            rows = (await db.scalars(select(RunnerEvent).where(RunnerEvent.job_id == job_id,
                RunnerEvent.seq > after).order_by(RunnerEvent.seq).limit(limit))).all()
            return [{'seq': r.seq, 'level': r.level, 'code': r.code, 'message': r.message,
                     'at': r.creation_date.isoformat(timespec='milliseconds') + 'Z'} for r in rows]

    async def heartbeat(self, worker_id, pid, process_created, status, active_job_id=None, error=None):
        async with self.sessions() as db:
            row = await db.get(RunnerWorker, 'local')
            values = dict(worker_id=worker_id, pid=pid, process_created=process_created, status=status,
                          active_job_id=active_job_id, heartbeat_at=now(), last_error=error, schema_version=1)
            if row:
                await db.execute(update(RunnerWorker).where(RunnerWorker.id == 'local').values(**values))
            else:
                db.add(RunnerWorker(id='local', **values))
            await db.commit()

    async def health(self):
        async with self.sessions() as db:
            row = await db.get(RunnerWorker, 'local')
            if not row:
                return {'status': 'offline', 'active_job_id': None}
            age = (now() - row.heartbeat_at).total_seconds()
            status = row.status if row.status == 'blocked' or (age < 10 and row.status != 'stopped') else 'offline'
            return {'status': status, 'worker_id': row.worker_id, 'pid': row.pid,
                    'active_job_id': row.active_job_id, 'heartbeat_age_seconds': max(0, round(age, 2)),
                    'last_error': row.last_error}
