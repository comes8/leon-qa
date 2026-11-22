from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWorkflow(StrictModel):
    project_id: int
    service_id: int
    environment_id: int
    writer_id: int
    reviewer_id: int
    title: str = Field(min_length=2, max_length=180)
    requirement: str = Field(min_length=10, max_length=24000)
    scope: Literal["local_mock", "project_qa", "binance_reference"] = "local_mock"
    knowledge_base_ids: list[int] = Field(min_length=1, max_length=8)


class CoveragePoint(StrictModel):
    id: str
    domain: str
    category: Literal["positive", "negative", "boundary", "exception", "business"]
    scenario: str
    expected: str
    priority: Literal["P0", "P1", "P2"]
    source_ids: list[int]
    rule_ids: list[str]
    needs_confirmation: bool = False


class RequirementAnalysis(StrictModel):
    summary: str
    domains: list[str]
    changed_behavior: list[str]
    regression_scope: list[str]
    open_questions: list[str]
    data_plan: list[str]
    coverage: list[CoveragePoint] = Field(min_length=1, max_length=35)

    @field_validator('coverage')
    @classmethod
    def unique_coverage(cls, coverage):
        ids = [point.id for point in coverage]
        if len(ids) != len(set(ids)):
            raise ValueError('coverage 的 id 必须唯一，每个不同覆盖点使用不同编号')
        return coverage


class Assertion(StrictModel):
    mode: Literal["jmespath", "jsonpath"]
    check: str = Field(min_length=1, max_length=240)
    comparator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_null", "is_null", "decimal_eq", "decimal_gte", "decimal_lte"] = "eq"
    expect: Any = None


class Extraction(StrictModel):
    name: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]{0,60}$")
    extract_type: Literal["jsonpath", "jmespath"] = "jsonpath"
    path: str = Field(min_length=1, max_length=240)


class RequestStep(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    api_id: int
    path_variables: dict[str, str | int] = Field(default_factory=dict)
    query: dict[str, Any] | None = None
    body: Any = None
    extracts: list[Extraction] = Field(default_factory=list, max_length=12)
    validators: list[Assertion] = Field(min_length=2, max_length=25)
    poll_attempts: int = Field(default=1, ge=1, le=10)
    poll_interval: float = Field(default=0.5, ge=0.1, le=5)


class Scenario(StrictModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{3,70}$")
    name: str = Field(min_length=2, max_length=180)
    category: Literal["positive", "negative", "boundary", "exception", "business"]
    priority: Literal["P0", "P1", "P2"]
    coverage_ids: list[str] = Field(min_length=1)
    source_ids: list[int] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    preconditions: list[str]
    expected: str
    blocked_reason: str = ""
    steps: list[RequestStep] = Field(default_factory=list, max_length=15)


class ScenarioPlan(StrictModel):
    scenarios: list[Scenario] = Field(min_length=1, max_length=25)

    @field_validator("scenarios")
    @classmethod
    def unique_ids(cls, scenarios):
        ids = [case.case_id for case in scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id 必须唯一")
        return scenarios


class ReviewIssue(StrictModel):
    case_id: str
    severity: Literal["blocking", "warning"]
    message: str


class PlanReview(StrictModel):
    verdict: Literal["pass", "revise"]
    summary: str
    issues: list[ReviewIssue]
    missing_coverage: list[str]


class ApproveWorkflow(StrictModel):
    revision: int
    case_ids: list[str] = Field(min_length=1, max_length=25)
    note: str = Field(default="", max_length=2000)
    acknowledge_review: bool = False


class ExecuteWorkflow(StrictModel):
    revision: int
    confirm_test_environment: bool


class UpdateDraft(StrictModel):
    revision: int
    draft: ScenarioPlan


class UpdateAnalysis(StrictModel):
    revision: int
    analysis: RequirementAnalysis
    note: str = Field(min_length=5, max_length=2000)
