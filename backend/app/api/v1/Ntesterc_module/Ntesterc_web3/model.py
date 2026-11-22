"""Persistent Web3 requirement-to-regression workflows."""
from sqlalchemy import BigInteger, Column, Integer, JSON, String, Text
from app.core.db_base import Base


class Web3WorkflowModel(Base):
    __tablename__ = "web3_qa_workflows"

    project_id = Column(BigInteger, nullable=False, index=True)
    service_id = Column(BigInteger, nullable=False)
    environment_id = Column(BigInteger, nullable=False)
    writer_id = Column(BigInteger, nullable=False)
    reviewer_id = Column(BigInteger, nullable=False)
    title = Column(String(200), nullable=False)
    requirement = Column(Text, nullable=False)
    scope = Column(String(30), nullable=False, default="local_mock")
    knowledge_base_ids = Column(JSON, nullable=False)
    status = Column(String(30), nullable=False, default="created", index=True)
    analysis = Column(JSON)
    citations = Column(JSON)
    draft = Column(JSON)
    review = Column(JSON)
    approval = Column(JSON)
    publication = Column(JSON)
    executions = Column(JSON)
    usage = Column(JSON)
    last_error = Column(Text)
    failed_stage = Column(String(30))
    revision = Column(Integer, nullable=False, default=1)
