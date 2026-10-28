"""组合评估接口（M3，实现方案 §4）：POST /api/portfolio/eval。

等权/手调权重可切换；权重缺省从 my_position 带出（份额×最新净值占比）。
基准入库走 POST /api/refresh?scope=index（沪深300 + 中证1000，新浪路由）。
"""
from fastapi import APIRouter, HTTPException

from ..db import conn
from ..schemas import (
    MetricOut, PortfolioEvalIn, PortfolioEvalOut, PortfolioMemberOut,
)
from ..services import portfolio as pf

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.post("/eval", response_model=PortfolioEvalOut)
def eval_portfolio(body: PortfolioEvalIn):
    weights = body.weights
    weight_mode = "manual"
    if weights is None:
        weights = pf.default_weights_from_positions(body.codes)
        weight_mode = "position" if weights else "equal"
    result = pf.evaluate(body.codes, weights, body.benchmark, weight_mode)
    if not result.get("codes"):
        raise HTTPException(409, f"无法评估：{'；'.join(result.get('data_gaps', []))}")

    members = []
    with conn() as c:
        for code in result["codes"]:
            fund = c.execute("SELECT name FROM fund WHERE code = ?", (code,)).fetchone()
            metric = c.execute(
                "SELECT * FROM fund_metric WHERE code = ? ORDER BY as_of DESC LIMIT 1",
                (code,)).fetchone()
            metric_row = dict(metric) if metric else None
            if metric_row:
                metric_row.pop("code", None)
            members.append(PortfolioMemberOut(
                code=code, name=(fund["name"] if fund else "") or code,
                weight=result["weights_used"].get(code, 0.0),
                metric=MetricOut(**metric_row) if metric_row else None))

    def _m_or_none(m: dict | None) -> MetricOut | None:
        return MetricOut(**m) if m else None

    return PortfolioEvalOut(
        codes=result["codes"],
        weights_used=result["weights_used"],
        weight_mode=result["weight_mode"],
        benchmark=result.get("benchmark"),
        benchmark_name=result.get("benchmark_name"),
        portfolio_metric=_m_or_none(result.get("portfolio_metric")),
        members=members,
        nav_dates=result.get("nav_dates", []),
        portfolio_nav=result.get("portfolio_nav", []),
        benchmark_nav=result.get("benchmark_nav", []),
        excess=result.get("excess", {}),
        corr_codes=result.get("corr_codes", []),
        corr_matrix=result.get("corr_matrix", []),
        data_gaps=result.get("data_gaps", []),
    )
