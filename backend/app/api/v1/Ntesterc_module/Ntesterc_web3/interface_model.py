from sqlalchemy import BigInteger,Column,Integer,JSON,String,Text,UniqueConstraint
from app.core.db_base import Base
from app.core.database import engine

class InterfacePlan(Base):
    __tablename__='web3_interface_plans'
    __table_args__=(UniqueConstraint('created_by','request_key',name='uq_web3_interface_plan_request'),)
    task_id=Column(BigInteger,nullable=False,index=True)
    project_id=Column(BigInteger,nullable=False,index=True)
    workflow_id=Column(BigInteger,nullable=False,unique=True)
    request_key=Column(String(80),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    parent_id=Column(BigInteger)
    version=Column(Integer,nullable=False,default=1)
    revision=Column(Integer,nullable=False,default=1)
    snapshot=Column(JSON,nullable=False)
    content=Column(JSON)
    origin=Column(String(20),nullable=False,default='model')
    note=Column(Text)
    busy_job_id=Column(BigInteger)

class InterfaceJob(Base):
    __tablename__='web3_interface_jobs'
    __table_args__=(UniqueConstraint('plan_id','created_by','request_key',name='uq_web3_interface_job_request'),)
    plan_id=Column(BigInteger,nullable=False,index=True)
    kind=Column(String(20),nullable=False)
    request_key=Column(String(80),nullable=False)
    request_fingerprint=Column(String(64),nullable=False)
    status=Column(String(20),nullable=False)
    input_snapshot=Column(JSON,nullable=False)
    candidate=Column(JSON)
    usage=Column(JSON)
    receipt=Column(JSON)
    cancel_note=Column(Text)
    error_message=Column(Text)

async def ensure_interface_schema():
    async with engine.begin() as conn:
        for cls in [InterfacePlan,InterfaceJob]:
            await conn.run_sync(lambda c,table=cls.__table__:table.create(c,checkfirst=True))
