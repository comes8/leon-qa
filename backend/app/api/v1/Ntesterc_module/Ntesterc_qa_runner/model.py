"""Owned task tables; business balances remain in separate test databases."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import BigInteger, Column, DateTime, Double, Index, Integer, JSON, String, Text, UniqueConstraint
from app.core.db_base import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RunnerJob(Base):
    __tablename__ = 'qa_runner_jobs'
    __table_args__ = (UniqueConstraint('project_id', 'user_id', 'request_key', name='uq_qa_runner_request'),
                      Index('ix_qa_runner_queue', 'status', 'creation_date'),)
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    creation_date = Column(DateTime, default=now, nullable=False)
    updation_date = Column(DateTime, default=now, onupdate=now, nullable=False)
    project_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    request_key = Column(String(80), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    project_key = Column(String(64), nullable=False)
    toolkit_root = Column(Text, nullable=False)
    suite_id = Column(String(64), nullable=False)
    suite_version = Column(String(32), nullable=False)
    run_kind = Column(String(16), nullable=False)
    run_id = Column(String(80), unique=True, nullable=False)
    output_dir = Column(Text, nullable=False)
    timeout_seconds = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default='queued')
    revision = Column(Integer, nullable=False, default=1)
    worker_id = Column(String(32))
    launch_token = Column(String(32), nullable=False)
    process_pid = Column(Integer)
    process_created = Column(Double)
    cancel_requested_at = Column(DateTime)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    result_status = Column(String(16))
    result = Column(JSON)
    process_exit_code = Column(Integer)
    cleanup_status = Column(String(24), nullable=False, default='not_started')
    error_message = Column(Text)


class RunnerEvent(Base):
    __tablename__ = 'qa_runner_events'
    __table_args__ = (UniqueConstraint('job_id', 'seq', name='uq_qa_runner_event_seq'),)
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    job_id = Column(String(32), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    level = Column(String(12), nullable=False, default='info')
    code = Column(String(48), nullable=False)
    message = Column(Text, nullable=False)
    creation_date = Column(DateTime, default=now, nullable=False)


class RunnerWorker(Base):
    __tablename__ = 'qa_runner_workers'
    id = Column(String(32), primary_key=True)
    worker_id = Column(String(32), nullable=False)
    pid = Column(Integer, nullable=False)
    process_created = Column(Double, nullable=False)
    status = Column(String(24), nullable=False)
    active_job_id = Column(String(32))
    heartbeat_at = Column(DateTime, nullable=False)
    last_error = Column(Text)
    schema_version = Column(Integer, nullable=False, default=1)


OWNED_TABLES = [RunnerJob.__table__, RunnerEvent.__table__, RunnerWorker.__table__]


async def ensure_schema(engine):
    from .lab_model import LAB_TABLES, ensure_lab_precision
    async with engine.begin() as connection:
        for table in OWNED_TABLES + LAB_TABLES:
            await connection.run_sync(lambda conn, table=table: table.create(conn, checkfirst=True))
        await connection.run_sync(ensure_lab_precision)
        await connection.run_sync(ensure_runner_precision)


def ensure_runner_precision(connection):
    """Only owned runner tables; preserve precise PID identities on MySQL."""
    if connection.dialect.name != 'mysql':
        return
    from sqlalchemy import inspect
    for table, nullable in [('qa_runner_jobs', 'NULL'), ('qa_runner_workers', 'NOT NULL')]:
        column = next(c for c in inspect(connection).get_columns(table) if c['name'] == 'process_created')
        if str(column['type']).upper().startswith('FLOAT'):
            connection.exec_driver_sql(f'ALTER TABLE {table} MODIFY process_created DOUBLE {nullable}')
