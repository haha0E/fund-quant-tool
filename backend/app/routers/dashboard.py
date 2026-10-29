"""仪表盘接口（M6，PRD FR4 首页）：持仓总览——收益/风险一眼看 + 数据新鲜度。

口径：组合加权指标按 my_position 份额×最新净值权重（无持仓份额时等权，
weight_mode 标注）；主题暴露按 domain_tags 聚合市值占比（策略页「单一主题
≤60%」红线的日常检查位）。
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter

from ..db import conn
from ..schemas import MetricOut
from ..services import portfolio as pf

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard():
    with conn() as c:
        holdings = c.execute(
            """SELECT f.code, f.name, f.domain_tags,
                      p.shares, p.market_value, p.value_as_of,
                      (SELECT as_of FROM fund_metric m WHERE m.code = f.code
                        ORDER BY as_of DESC LIMIT 1) AS metric_as_of
               FROM fund f LEFT JOIN my_position p ON p.code = f.code
               WHERE f.pool_type = 'holding' ORDER BY f.code""").fetchall()
        metrics = {r["code"]: r for r in c.execute(
            "SELECT * FROM fund_metric WHERE as_of ="
            " (SELECT MAX(as_of) FROM fund_metric)")}
        nav_latest = dict(c.execute(
            "SELECT code, MAX(date) FROM fund_nav GROUP BY code").fetchall())
        h_latest = c.execute(
            "SELECT code, MAX(report_date) AS rd FROM fund_holding GROUP BY code").fetchall()
        gaps_count = c.execute(
            "SELECT COUNT(*) FROM fund WHERE code NOT IN"
            " (SELECT DISTINCT code FROM fund_nav)").fetchone()[0]

    today = date.today()
    rows = []
    theme_value: dict[str, float] = {}
    total_value = 0.0
    for h in holdings:
        m = metrics.get(h["code"])
        lag = None
        rd = next((r["rd"] for r in h_latest if r["code"] == h["code"]), None)
        if rd:
            lag = (today - datetime.strptime(rd, "%Y-%m-%d").date()).days
        mv = h["market_value"] or 0.0
        total_value += mv
        for t in (h["domain_tags"] or "").split(","):
            if t.strip():
                theme_value[t.strip()] = theme_value.get(t.strip(), 0.0) + mv
        rows.append({
            "code": h["code"], "name": h["name"] or h["code"],
            "domain_tags": [t for t in (h["domain_tags"] or "").split(",") if t],
            "shares": h["shares"], "market_value": h["market_value"],
            "value_as_of": h["value_as_of"],
            "nav_as_of": nav_latest.get(h["code"]),
            "holding_lag_days": lag,
            "ret_ytd": m["ret_ytd"] if m else None,
            "ret_1y": m["ret_1y"] if m else None,
            "max_dd": m["max_dd"] if m else None,
            "sharpe": m["sharpe"] if m else None,
        })

    # 组合加权指标（份额权重；无份额回退等权并标注）
    codes = [r["code"] for r in rows]
    weight_mode = "equal"
    portfolio_metric = None
    if codes:
        weights = pf.default_weights_from_positions(codes)
        if weights:
            weight_mode = "position"
        else:
            weights = {c2: 1.0 / len(codes) for c2 in codes}
        portfolio_metric = pf.evaluate(codes, weights,
                                       benchmark=None)["portfolio_metric"]

    theme_exposure = [
        {"theme": t, "value": v,
         "pct": (v / total_value) if total_value > 0 else None}
        for t, v in sorted(theme_value.items(), key=lambda kv: -kv[1])
    ] if total_value > 0 else []

    return {
        "as_of": date.today().isoformat(),
        "holdings": rows,
        "total_market_value": total_value or None,
        "weight_mode": weight_mode,
        "portfolio_metric": MetricOut(**portfolio_metric) if portfolio_metric else None,
        "theme_exposure": theme_exposure,
        "theme_limit": 0.60,  # 策略页红线：单一主题 ≤60%
        "no_nav_funds": gaps_count,
    }
