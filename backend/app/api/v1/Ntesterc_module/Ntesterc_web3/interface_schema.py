"""Business-case to registered HTTP scenario adapter; no arbitrary URL or code."""
from typing import Literal
from pydantic import Field
from .design_schema import Strict
from .schema import RequestStep, Scenario

class MappedStep(RequestStep):
    business_steps: list[int] = Field(default_factory=list, max_length=12)
    purpose: Literal['setup','action','observe','cleanup']
    rationale: str = Field(min_length=3,max_length=1200)

class Preparation(Strict):
    item: str = Field(min_length=3,max_length=1200)
    status: Literal['documented','needs_preparation','not_applicable']
    api_ids: list[int] = Field(default_factory=list,max_length=15)
    basis: str = Field(min_length=3,max_length=2000)

class MappedCase(Scenario):
    steps: list[MappedStep] = Field(default_factory=list,max_length=20)
    preparations: list[Preparation] = Field(min_length=1,max_length=15)
    execution_gaps: list[str] = Field(default_factory=list,max_length=20)
    observation_limitations: list[str] = Field(min_length=1,max_length=15)

class InterfaceOutput(Strict):
    summary: str = Field(min_length=3,max_length=6000)
    scenarios: list[MappedCase] = Field(min_length=1,max_length=12)

class CreatePlan(Strict):
    task_id: int
    title: str = Field(min_length=2,max_length=180)
    service_id: int
    environment_id: int
    scope: Literal['local_mock','project_qa','reference_only'] = 'local_mock'
    case_ids: list[str] = Field(min_length=1,max_length=12)
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')

class GeneratePlan(Strict):
    expected_revision: int
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    instruction: str = Field(default='',max_length=6000)
    preview_hash: str | None = None

class RevisePlan(Strict):
    expected_revision: int
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    content: InterfaceOutput
    note: str = Field(min_length=5,max_length=2000)

class PublishPlan(Strict):
    expected_revision: int
    case_ids: list[str] = Field(min_length=1,max_length=12)
    note: str = Field(min_length=8,max_length=2000)
    confirm_mapping: bool

class RunPlan(Strict):
    expected_revision: int
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    confirm_test_environment: bool

class CancelRun(Strict):
    note: str = Field(min_length=5,max_length=2000)
