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
    position: "PositionOut | None" = None  # my_position（持仓池录入，M3）
    data_gaps: list[str] = []          # 数据缺口显式标注（不静默造假）


# ---- M3：持仓份额录入（权重默认 = 份额×最新净值） ----

class PositionIn(BaseModel):
    shares: float = Field(gt=0, le=1e9)


class PositionOut(BaseModel):
    code: str
    shares: float
    market_value: float | None = None
    value_as_of: str | None = None
    updated_at: str


# ---- M3：预检入池（走 ingest 拉预览，不入库） ----

class PreflightOut(BaseModel):
    code: str
    name: str = ""
    fund_type: str | None = None
    company: str | None = None
    manager: str | None = None
    scale: str | None = None
    inception_date: str | None = None
    latest_nav_date: str | None = None
    ret_1y: float | None = None
    ret_ytd: float | None = None
    integrity_bad: bool = False        # 差值负向漂移（110005 先例）→ 收益不采信
    warnings: list[str] = []
    suggested_tags: list[str] = []     # 领域标签推断（保守关键词规则，可核对）


# ---- M3：结论自动草稿 ----

class NoteDraftOut(BaseModel):
    draft: str


# ---- M3：策略页（data/strategy 只读渲染） ----

class StrategyFileOut(BaseModel):
    filename: str
    title: str
    updated_at: str


# ---- M3：组合评估（POST /api/portfolio/eval） ----

class PortfolioEvalIn(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=20)
    weights: dict[str, float] | None = None   # code->权重（任意正数，内部归一）；None=自动
    benchmark: str | None = "sh000300"        # None 表示不算基准超额


class PortfolioMemberOut(BaseModel):
    code: str
    name: str
    weight: float                          # 归一后占比（小数）
    metric: MetricOut | None = None


class PortfolioEvalOut(BaseModel):
    codes: list[str]
    weights_used: dict[str, float]
    weight_mode: str                       # position(份额×净值)/equal(等权)/manual(手调)
    benchmark: str | None = None
    benchmark_name: str | None = None
    portfolio_metric: MetricOut | None = None
    members: list[PortfolioMemberOut] = []
    nav_dates: list[str] = []              # 组合合成净值（共同交易日对齐）
    portfolio_nav: list[float] = []
    benchmark_nav: list[float] = []        # 对齐后基准（与 portfolio_nav 同长；无基准为空）
    excess: dict[str, float | None] = {}   # ret_1m/3m/6m/ytd/1y 超额（对齐后同窗相减）
    corr_codes: list[str] = []
    corr_matrix: list[list[float | None]] = []
    data_gaps: list[str] = []
