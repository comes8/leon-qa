from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LabRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0, strict=True)
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-z0-9][a-z0-9_-]+$')
    action: Literal['start', 'stop', 'create', 'inspect', 'rebuild', 'delete', 'transfer', 'query', 'verify']
    environment_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    dataset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    funding: str | None = Field(default=None, pattern=r'^[0-9]{1,8}(\.[0-9]{1,8})?$')
    spot: str | None = Field(default=None, pattern=r'^[0-9]{1,8}(\.[0-9]{1,8})?$')
    test_user: Literal['alice', 'bob'] | None = None
    business_request_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$')
    from_account: Literal['funding', 'spot'] | None = None
    to_account: Literal['funding', 'spot'] | None = None
    amount: str | None = Field(default=None, pattern=r'^[0-9]{1,8}(\.[0-9]{1,8})?$')
    expected_funding: str | None = Field(default=None, pattern=r'^[0-9]{1,8}(\.[0-9]{1,8})?$')
    expected_spot: str | None = Field(default=None, pattern=r'^[0-9]{1,8}(\.[0-9]{1,8})?$')
    expected_status: Literal['SUCCEEDED', 'REJECTED'] | None = None
    requirement_ref: str | None = Field(default=None, max_length=120)
    case_ref: str | None = Field(default=None, max_length=120)
    review_note: str | None = Field(default=None, max_length=1000)

    @field_validator('amount')
    @classmethod
    def transfer_amount(cls, value):
        if value is not None and not 0 < Decimal(value) <= Decimal('10000000'):
            raise ValueError('划转金额必须大于0且不超过10000000')
        return value

    @field_validator('expected_funding', 'expected_spot')
    @classmethod
    def expected_balance(cls, value):
        if value is not None and Decimal(value) > Decimal('20000000'):
            raise ValueError('预期余额不能超过本机样例总额上界20000000')
        return value

    @field_validator('requirement_ref', 'case_ref', 'review_note')
    @classmethod
    def association_text(cls, value):
        if value is not None and any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('关联内容含控制字符')
        return value

    @field_validator('name')
    @classmethod
    def readable_name(cls, value):
        if value is not None and (not value.strip() or any(ord(c) < 32 for c in value)):
            raise ValueError('数据集名称不能为空或包含控制字符')
        return value

    @field_validator('funding', 'spot')
    @classmethod
    def permitted_seed(cls, value):
        if value is not None and Decimal(value) > Decimal('10000000'):
            raise ValueError('初始金额不能超过 10000000 TESTUSD')
        return value

    @model_validator(mode='after')
    def exact_fields(self):
        supplied = {k for k, v in self.model_dump().items() if v is not None} - {'project_id', 'request_key', 'action'}
        common = {'environment_id', 'dataset_id', 'expected_revision'}
        debug = common | {'test_user', 'business_request_id'}
        transfer = debug | {'from_account', 'to_account', 'amount'}
        expected = {'start': set(), 'stop': {'environment_id'},
                    'create': {'environment_id', 'name', 'funding', 'spot'},
                    'inspect': {'environment_id', 'dataset_id', 'expected_revision'},
                    'rebuild': {'environment_id', 'dataset_id', 'expected_revision'},
                    'delete': common, 'transfer': transfer, 'query': debug,
                    'verify': transfer | {'expected_funding', 'expected_spot', 'expected_status'}}[self.action]
        if self.action in {'transfer', 'query', 'verify'}:
            supplied -= {'requirement_ref', 'case_ref', 'review_note'}
        if self.action in {'transfer', 'verify'} and self.from_account == self.to_account:
            raise ValueError('资金和现货之间划转，不允许相同账户方向')
        if supplied != expected:
            raise ValueError('此操作的字段不完整或包含不允许的参数')
        return self
