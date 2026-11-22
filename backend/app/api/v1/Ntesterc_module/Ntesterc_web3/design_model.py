from sqlalchemy import BigInteger, Column, Integer, JSON, String, Text, UniqueConstraint
from app.core.db_base import Base
from app.core.database import engine


class DesignTask(Base):
    __tablename__ = 'web3_design_tasks'
    __table_args__ = (UniqueConstraint('created_by', 'request_key', name='uq_web3_design_task_request'),)
    project_id = Column(BigInteger, nullable=False, index=True)
    request_key = Column(String(80), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    title = Column(String(200), nullable=False)
    requirement = Column(Text, nullable=False)
    background = Column(Text, nullable=False)
    scope = Column(String(40), nullable=False)
    bundle_id = Column(BigInteger, nullable=False)
    writer_id = Column(BigInteger, nullable=False)
    reviewer_id = Column(BigInteger, nullable=False)
    specialist_keys = Column(JSON, nullable=False)
    knowledge_document_ids = Column(JSON, nullable=False)
    source_snapshot = Column(JSON, nullable=False)
    input_history = Column(JSON, nullable=False)
    heads = Column(JSON, nullable=False)
    input_revision = Column(Integer, nullable=False, default=1)
    revision = Column(Integer, nullable=False, default=1)
    busy_job_id = Column(BigInteger)


class DesignArtifact(Base):
    __tablename__ = 'web3_design_artifacts'
    __table_args__ = (UniqueConstraint('task_id', 'stage', 'version', name='uq_web3_design_artifact_version'),)
    task_id = Column(BigInteger, nullable=False, index=True)
    stage = Column(String(40), nullable=False)
    version = Column(Integer, nullable=False)
    input_revision = Column(Integer, nullable=False)
    parent_ids = Column(JSON, nullable=False)
    content = Column(JSON, nullable=False)
    provenance = Column(JSON, nullable=False)
    origin = Column(String(20), nullable=False)
    note = Column(Text)
    confirmation = Column(JSON)


class DesignJob(Base):
    __tablename__ = 'web3_design_jobs'
    __table_args__ = (UniqueConstraint('task_id', 'created_by', 'request_key', name='uq_web3_design_job_request'),)
    task_id = Column(BigInteger, nullable=False, index=True)
    request_key = Column(String(80), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    stage = Column(String(40), nullable=False)
    prompt_key = Column(String(10), nullable=False)
    status = Column(String(30), nullable=False)
    input_snapshot = Column(JSON, nullable=False)
    candidate = Column(JSON)
    artifact_id = Column(BigInteger)
    error_message = Column(Text)
    usage = Column(JSON)


async def ensure_design_schema():
    async with engine.begin() as connection:
        for model in (DesignTask, DesignArtifact, DesignJob):
            await connection.run_sync(lambda conn, table=model.__table__: table.create(conn, checkfirst=True))
