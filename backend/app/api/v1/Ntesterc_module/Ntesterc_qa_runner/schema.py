from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class CreateJob(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0, strict=True)
    project_key: Literal['leon-qa-kit'] = 'leon-qa-kit'
    suite_id: Literal['funds-transfer-v1'] = 'funds-transfer-v1'
    run_kind: Literal['regression', 'selftest'] = 'regression'
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-z0-9][a-z0-9_-]+$')
    timeout_seconds: int = Field(default=300, ge=1, le=900, strict=True)
