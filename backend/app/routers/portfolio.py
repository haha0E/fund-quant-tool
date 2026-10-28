"""组合评估接口（M3，实现方案 §4）+ 穿透分析接口（M4，PRD FR2③/FR3）。

- POST /api/portfolio/eval：等权/手调权重可切换；权重缺省从 my_position 带出。
- GET  /api/portfolio/overlap：同名重仓股合并、穿透权重、未披露部分、报告期滞后。
基准入库走 POST /api/refresh?scope=index（沪深300 + 中证1000，新浪路由）；
个股行情/估值走 POST /api/refresh?scope=stocks&symbols=300502,300308。
"""
from fastapi import APIRouter, HTTPException, Query

from ..db import conn
from ..schemas import (
    MetricOut, OverlapOut, PortfolioEvalIn, PortfolioEvalOut, PortfolioMemberOut,
)
from ..services import overlap as ol
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


def _resolve_weights(codes: list[str], w: list[float] | None) -> tuple[dict[str, float], str]:
    """权重归一：手调（w 与 codes 对应）→ 持仓份额 → 等权。返回 (weights, mode)。"""
    if w is not None:
        if len(w) != len(codes) or any(x < 0 for x in w) or sum(w) <= 0:
            raise HTTPException(400, "w 须与 codes 等长、非负且不全为 0")
        total = sum(w)
        return {c: x / total for c, x in zip(codes, w)}, "manual"
    got = pf.default_weights_from_positions(codes)
    if got:
        return got, "position"
    return {c: 1.0 / len(codes) for c in codes}, "equal"


@router.get("/overlap", response_model=OverlapOut)
def portfolio_overlap(codes: str = Query(..., description="逗号分隔基金代码"),
                      w: str | None = Query(None, description="逗号分隔权重（与 codes 对应，缺省自动")):
    """穿透分析（M4）：前十大合并穿透 + 个股量化指标 + 未披露部分 + 滞后标注。"""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        raise HTTPException(400, "codes 不能为空")
    weights, _mode = _resolve_weights(code_list,
                                      [float(x) for x in w.split(",")] if w else None)
    result = ol.overlap(code_list, weights)
    if not result.get("members"):
        raise HTTPException(409, f"无法穿透：{'；'.join(result.get('data_gaps', []))}")
    return OverlapOut(**result)
