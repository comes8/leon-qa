"""Business-design contracts, deliberately separate from executable API scenarios."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


Readiness = Literal['ready', 'partial', 'blocked']
Stage = Literal['analysis', 'requirement_review', 'modeling', 'spot', 'futures', 'funds',
                'testpoints', 'testpoint_review', 'cases', 'case_review', 'regression']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class SourceRef(Strict):
    source_id: str = Field(min_length=1, max_length=90)
    locator: str = Field(min_length=1, max_length=400)


class Question(Strict):
    id: str = Field(min_length=1, max_length=70)
    question: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    affected_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)


class CommonOutput(Strict):
    summary: str = Field(min_length=1, max_length=6000)
    readiness: Readiness
    notes: list[str] = Field(default_factory=list, max_length=40)
    questions: list[Question] = Field(default_factory=list, max_length=30)


class Requirement(Strict):
    id: str
    goal: str
    source_refs: list[SourceRef] = Field(min_length=1)


class Rule(Strict):
    id: str
    statement: str
    scope: str
    evidence_kind: Literal['stated', 'observed', 'proposed', 'unknown', 'conflict']
    source_refs: list[SourceRef] = Field(min_length=1)
    unresolved: list[str] = Field(default_factory=list)


class Risk(Strict):
    id: str
    risk: str
    impact: str
    source_refs: list[SourceRef] = Field(min_length=1)


class Acceptance(Strict):
    id: str
    conditions: str
    action: str
    expected: str
    verification: str
    rule_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)


class AnalysisOutput(CommonOutput):
    requirements: list[Requirement] = Field(min_length=1, max_length=25)
    rules: list[Rule] = Field(min_length=1, max_length=40)
    risks: list[Risk] = Field(default_factory=list, max_length=25)
    acceptance: list[Acceptance] = Field(default_factory=list, max_length=25)


class Entity(Strict):
    id: str
    name: str
    states: list[str]
    observation: str
    source_refs: list[SourceRef] = Field(min_length=1)


class Transition(Strict):
    id: str
    entity_id: str
    from_state: str
    event: str
    guard: str
    to_state: str
    effect: str
    observation: str
    rule_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)


class Invariant(Strict):
    id: str
    condition: str
    formula_or_property: str
    units_and_phase: str
    independent_evidence: str
    rule_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)


class ModelingOutput(CommonOutput):
    entities: list[Entity] = Field(min_length=1, max_length=15)
    transitions: list[Transition] = Field(default_factory=list, max_length=30)
    invariants: list[Invariant] = Field(min_length=1, max_length=25)


class Testpoint(Strict):
    id: str
    title: str
    rule_ids: list[str] = Field(min_length=1)
    model_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(min_length=1)
    conditions: list[str] = Field(min_length=1)
    trigger: str
    expected: str
    verification: str
    priority: Literal['P0', 'P1', 'P2']
    design_readiness: Readiness
    execution_readiness: Literal['known_available', 'needs_preparation', 'capability_unknown']
    unresolved: list[str] = Field(default_factory=list)


class TestpointOutput(CommonOutput):
    testpoints: list[Testpoint] = Field(min_length=1, max_length=20)


class Step(Strict):
    action: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    observation: str = Field(min_length=1)


class BusinessCase(Strict):
    id: str
    title: str
    testpoint_ids: list[str] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    source_refs: list[SourceRef] = Field(min_length=1)
    preconditions: list[str] = Field(min_length=1)
    data: list[str] = Field(min_length=1)
    steps: list[Step] = Field(min_length=1, max_length=12)
    expected_result: str = Field(min_length=1)
    cleanup: list[str] = Field(default_factory=list)
    priority: Literal['P0', 'P1', 'P2']
    design_readiness: Readiness
    execution_readiness: Literal['known_available', 'needs_preparation', 'capability_unknown']
    unresolved: list[str] = Field(default_factory=list)


class CaseOutput(CommonOutput):
    cases: list[BusinessCase] = Field(min_length=1, max_length=12)


class ReviewIssue(Strict):
    id: str
    target_ids: list[str]
    category: str
    severity: Literal['blocking', 'important', 'minor']
    problem: str
    consequence: str
    suggestion: str
    source_refs: list[SourceRef] = Field(min_length=1)


class ReviewOutput(CommonOutput):
    decision: Literal['continue', 'revise', 'blocked']
    reviewed_scope: str
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=40)
    missing_coverage: list[str] = Field(default_factory=list, max_length=25)
    execution_gaps: list[str] = Field(default_factory=list, max_length=25)


class SpecialistOutput(CommonOutput):
    findings: list[Risk] = Field(min_length=1, max_length=25)
    invariants: list[Invariant] = Field(default_factory=list, max_length=25)


class RegressionSelection(Strict):
    case_id: str
    disposition: Literal['reuse', 'revise', 'add', 'blocked', 'defer']
    reason: str
    prerequisites: list[str]
    source_refs: list[SourceRef] = Field(min_length=1)


class RegressionOutput(CommonOutput):
    impacts: list[Risk] = Field(min_length=1, max_length=25)
    selection: list[RegressionSelection] = Field(default_factory=list, max_length=30)
    remaining_risks: list[str] = Field(default_factory=list, max_length=30)


class PointPatch(Strict):
    summary: str
    testpoints: list[Testpoint] = Field(min_length=1, max_length=20)


class CasePatch(Strict):
    summary: str
    cases: list[BusinessCase] = Field(min_length=1, max_length=12)


class TaskInput(Strict):
    title: str = Field(min_length=2, max_length=180)
    requirement: str = Field(min_length=15, max_length=24000)
    background: str = Field(default='', max_length=16000)
    scope: Literal['local_synthetic', 'project_design', 'reference_design'] = 'project_design'
    bundle_id: int
    writer_id: int
    reviewer_id: int
    specialist_keys: list[Literal['cex-spot-matching', 'cex-futures-risk', 'cex-funds-reconciliation']] = Field(default_factory=list, max_length=3)
    knowledge_document_ids: list[int] = Field(default_factory=list, max_length=12)


class CreateDesign(TaskInput):
    project_id: int
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')


class UpdateDesign(TaskInput):
    expected_revision: int
    note: str = Field(min_length=5, max_length=2000)


class StageRequest(Strict):
    expected_revision: int
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    stage: Stage
    prompt_key: str
    instruction: str = Field(default='', max_length=5000)
    item_ids: list[str] = Field(default_factory=list, max_length=20)
    case_testpoint_ids: list[str] = Field(default_factory=list, max_length=20)
    max_items: int = Field(default=8, ge=1, le=12)
    preview_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class ConfirmArtifact(Strict):
    expected_revision: int
    artifact_id: int
    note: str = Field(min_length=5, max_length=2000)
    accept_partial: bool = False
    override_review_issues: bool = False


class EditArtifact(Strict):
    expected_revision: int
    artifact_id: int
    content: dict
    note: str = Field(min_length=5, max_length=2000)


class ManualStage(Strict):
    expected_revision: int
    stage: Stage
    prompt_key: str
    content: dict
    note: str = Field(min_length=5, max_length=2000)
