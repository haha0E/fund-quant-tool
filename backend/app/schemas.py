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


# ---- M2：单基金画像详情（档案+指标+持仓+净值+结论） ----

PROFILE_FIELDS = (
    "name", "full_name", "fund_type", "inception_date", "scale", "company",
    "manager", "custodian", "rating", "benchmark", "objective", "strategy",
    "fee_management", "fee_custody", "fee_subscription", "fee_redemption",
    "stock_position", "stock_position_as_of", "tracked_index", "as_of", "source",
)


class NavPoint(BaseModel):
    date: str
    unit_nav: float
    acc_nav: float | None = None
    dividend: float = 0.0


class DividendEvent(BaseModel):
    date: str
    dividend: float


class MetricOut(BaseModel):
    as_of: str | None = None
    ret_1m: float | None = None
    ret_3m: float | None = None
    ret_6m: float | None = None
    ret_ytd: float | None = None
    ret_1y: float | None = None
    ann_ret: float | None = None
    max_dd: float | None = None
    ann_vol: float | None = None
    sharpe: float | None = None


class HoldingOut(BaseModel):
    report_date: str
    stock_code: str
    stock_name: str
    weight: float


class FundDetailOut(BaseModel):
    code: str
    name: str
    pool_type: PoolType
    domain_tags: list[str]
    profile: dict | None = None        # 20 字段（as_of 最新一条），缺摄取时为 null
    metric: MetricOut | None = None
    nav: list[NavPoint] = []
    dividends: list[DividendEvent] = []
    holdings: list[HoldingOut] = []    # 最新报告期前十
    holding_periods: list[str] = []    # 库内已有报告期（降序），供界面切换（M2 先只显最新）
    note: str = ""
    note_updated_at: str | None = None
    data_gaps: list[str] = []          # 数据缺口显式标注（不静默造假）
