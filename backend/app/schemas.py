"""API 请求/响应模型（Pydantic）。"""
from typing import Literal

from pydantic import BaseModel, Field

PoolType = Literal["holding", "research"]


class FundIn(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    name: str = Field(min_length=1, max_length=50)
    pool_type: PoolType = "research"
    domain_tags: list[str] = Field(default_factory=list, max_length=5)


class FundPatch(BaseModel):
    name: str | None = None
    pool_type: PoolType | None = None
    domain_tags: list[str] | None = None


class FundOut(BaseModel):
    code: str
    name: str
    pool_type: PoolType
    domain_tags: list[str]
    created_at: str
    has_note: bool = False


class NoteIn(BaseModel):
    content: str = Field(max_length=20000)


class NoteOut(BaseModel):
    fund_code: str
    content: str
    updated_at: str


class HealthOut(BaseModel):
    status: str
    db_path: str
    fund_count: int
