"""Manual fixture environments are separate from regression jobs and balances."""
from uuid import uuid4
from sqlalchemy import BigInteger, Column, Double, Integer, JSON, String, Text, UniqueConstraint
from app.core.db_base import Base
from .model import now
from sqlalchemy import DateTime


class LabEnvironment(Base):
    __tablename__ = 'qa_lab_environments'
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    active_slot = Column(String(80), unique=True)
    capacity_slot = Column(Integer, unique=True)
    status = Column(String(24), nullable=False)
    session_id = Column(String(40), nullable=False, unique=True)
    launch_token = Column(String(32), nullable=False)
    registration = Column(JSON, nullable=False)
    process_pid = Column(Integer)
    process_created = Column(Double)
    source_sha256 = Column(String(64))
    cleanup_status = Column(String(24), nullable=False, default='not_started')
    error_message = Column(Text)
    creation_date = Column(DateTime, default=now, nullable=False)
    updation_date = Column(DateTime, default=now, onupdate=now, nullable=False)


class LabDataset(Base):
    __tablename__ = 'qa_lab_datasets'
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    environment_id = Column(String(32), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    funding = Column(String(32), nullable=False)
    spot = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    generation = Column(Integer, nullable=False, default=0)
    native_id = Column(String(80))
    snapshot = Column(JSON)
    history = Column(JSON, nullable=False, default=list)
    error_message = Column(Text)
    creation_date = Column(DateTime, default=now, nullable=False)
    updation_date = Column(DateTime, default=now, onupdate=now, nullable=False)


class LabOperation(Base):
    __tablename__ = 'qa_lab_operations'
    __table_args__ = (UniqueConstraint('project_id', 'user_id', 'request_key', name='uq_qa_lab_request'),)
    id = Column(String(32), primary_key=True, default=lambda: uuid4().hex)
    project_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    environment_id = Column(String(32), nullable=False, index=True)
    dataset_id = Column(String(32))
    busy_slot = Column(String(32), unique=True)
    action = Column(String(16), nullable=False)
    request_key = Column(String(80), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    inputs = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False)
    result = Column(JSON)
    error_message = Column(Text)
    creation_date = Column(DateTime, default=now, nullable=False)
    updation_date = Column(DateTime, default=now, onupdate=now, nullable=False)


LAB_TABLES = [LabEnvironment.__table__, LabDataset.__table__, LabOperation.__table__]


def ensure_lab_precision(connection):
    # Only the new phase-four table: earlier prototypes may have used MySQL FLOAT32.
    if connection.dialect.name == 'mysql':
        from sqlalchemy import inspect
        column = next(c for c in inspect(connection).get_columns('qa_lab_environments') if c['name'] == 'process_created')
        if str(column['type']).upper().startswith('FLOAT'):
            connection.exec_driver_sql('ALTER TABLE qa_lab_environments MODIFY process_created DOUBLE NULL')
