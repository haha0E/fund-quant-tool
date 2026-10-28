"""穿透分析计算层（M4，PRD FR2③/FR3）。

口径（§6 穿透权重行 + FR3 口径诚实）：
- 穿透权重 = Σ(基金权重 × 个股占净值比/100)，按股票代码合并（前十大截面）；
- 未披露部分 = 1 − Σ(基金权重 × 该基金前十大合计占比/100)——防穿透精度被高估；
- 有效持仓数 = 穿透权重 ≥1% 的个股数（阈值界面标注）；
- 报告期滞后按基金标注（最新 report_date 距今天数），表级取最保守（最大滞后）；
- 个股指标来自 stock_daily（新浪前复权）/stock_valuation（百度 PE/PB），
  缺数据返回 None 并计入 gaps，不造假；港股/美股代码无新浪路由，显式标注。
- 标色阈值（PRD 评分哲学）：单股组合权重 >10% 红。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..db import conn
from .metrics import (
    Series, max_drawdown, ann_volatility, percentile_of_latest, window_return,
)

EFFECTIVE_MIN_WEIGHT = 0.01   # 有效持仓数阈值：穿透权重 ≥1%
OVER_LIMIT = 0.10             # 标色阈值：单股组合权重 >10% 红（PRD）


def _a_share_sina_symbol(stock_code: str) -> str | None:
    if len(stock_code) == 6 and stock_code.isdigit():
        return ("sh" if stock_code.startswith(("6", "9")) else "sz") + stock_code
    return None


def _stock_metrics(sina_symbol: str, bare_code: str) -> dict:
    """个股量化指标（库内已摄取的序列；缺则 None，由 gaps 层标注）。"""
    with conn() as c:
        d_rows = c.execute(
            "SELECT date, close FROM stock_daily WHERE symbol = ? ORDER BY date",
            (sina_symbol,)).fetchall()
        v_rows = c.execute(
            "SELECT date, pe_ttm, pb FROM stock_valuation WHERE symbol = ? ORDER BY date",
            (bare_code,)).fetchall()
    out: dict = {"ret_3m": None, "ret_6m": None, "ret_ytd": None, "pos_52w": None,
                 "ann_vol": None, "max_dd_1y": None,
                 "pe_ttm": None, "pb": None, "pe_pct": None, "pb_pct": None,
                 "as_of": None}
    if len(d_rows) >= 2:
        dates = [r["date"] for r in d_rows]
        closes = [r["close"] for r in d_rows]
        s = Series(dates, closes)
        as_of = dates[-1]
        out["as_of"] = as_of
        out["ret_3m"] = window_return(s, _shift(as_of, -91))
        out["ret_6m"] = window_return(s, _shift(as_of, -182))
        out["ret_ytd"] = window_return(s, _shift(f"{as_of[:4]}-01-01", -1))
        # 52 周高低位置：近 252 个交易日区间 (close-min)/(max-min)
        win = closes[-252:] if len(closes) >= 252 else closes
        lo, hi = min(win), max(win)
        out["pos_52w"] = (closes[-1] - lo) / (hi - lo) if hi > lo else None
        out["ann_vol"] = ann_volatility(s)
        i0 = max(0, len(dates) - 252)  # 近 1 年窗口回撤
        out["max_dd_1y"] = max_drawdown(dates[i0:], closes[i0:])
    if v_rows:
        out["pe_ttm"] = v_rows[-1]["pe_ttm"]
        out["pb"] = v_rows[-1]["pb"]
        out["pe_pct"] = percentile_of_latest([r["pe_ttm"] for r in v_rows])
        out["pb_pct"] = percentile_of_latest([r["pb"] for r in v_rows])
    return out


def _shift(date_str: str, days: int) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def overlap(codes: list[str], weights: dict[str, float]) -> dict:
    """穿透主入口。weights 已归一（基金权重合计 1）。"""
    gaps: list[str] = []
    today = date.today()
    members: list[dict] = []
    stock_acc: dict[str, dict] = {}   # stock_code -> 累计权重与来源

    with conn() as c:
        for code in codes:
            fund = c.execute("SELECT name FROM fund WHERE code = ?", (code,)).fetchone()
            rows = c.execute(
                "SELECT report_date, stock_code, stock_name, weight FROM fund_holding"
                " WHERE code = ? ORDER BY report_date DESC", (code,)).fetchall()
            if not rows:
                gaps.append(f"{code} 无持仓披露（先刷新 holdings）")
                continue
            latest = rows[0]["report_date"]
            top10 = [r for r in rows if r["report_date"] == latest]
            lag = (today - datetime.strptime(latest, "%Y-%m-%d").date()).days
            members.append({"code": code, "name": (fund["name"] if fund else "") or code,
                            "weight": weights.get(code, 0.0), "report_date": latest,
                            "lag_days": lag, "top10_sum": sum(r["weight"] for r in top10) / 100})
            for r in top10:
                acc = stock_acc.setdefault(r["stock_code"],
                                           {"stock_name": r["stock_name"], "weight": 0.0,
                                            "funds": []})
                contrib = weights.get(code, 0.0) * (r["weight"] or 0) / 100
                acc["weight"] += contrib
                acc["funds"].append({"code": code, "weight_pct": r["weight"], "contrib": contrib})

    if not members:
        return {"data_gaps": gaps or ["无可用成员"], "stocks": [], "members": []}

    # 未披露部分 = 1 − Σ(基金权重 × 前十大合计占比)
    disclosed = sum(m["weight"] * m["top10_sum"] for m in members)
    undisclosed = max(0.0, 1 - disclosed)

    stocks = []
    for stock_code, acc in stock_acc.items():
        sina = _a_share_sina_symbol(stock_code)
        entry = {"stock_code": stock_code, "stock_name": acc["stock_name"],
                 "weight": acc["weight"], "fund_count": len(acc["funds"]),
                 "funds": acc["funds"], "a_share": sina is not None,
                 **( _stock_metrics(sina, stock_code) if sina else
                     {"ret_3m": None, "ret_6m": None, "ret_ytd": None, "pos_52w": None,
                      "ann_vol": None, "max_dd_1y": None, "pe_ttm": None, "pb": None,
                      "pe_pct": None, "pb_pct": None, "as_of": None})}
        stocks.append(entry)
    stocks.sort(key=lambda s: s["weight"], reverse=True)

    effective = sum(1 for s in stocks if s["weight"] >= EFFECTIVE_MIN_WEIGHT)
    max_lag = max(m["lag_days"] for m in members)
    no_quote = [s["stock_code"] for s in stocks if s["a_share"] and s["as_of"] is None]
    if no_quote:
        gaps.append(f"个股行情未摄取（穿透页点「刷新个股数据」）：{'/'.join(no_quote[:6])}"
                    + ("…" if len(no_quote) > 6 else ""))
    hk_us = [s["stock_code"] for s in stocks if not s["a_share"]]
    if hk_us:
        gaps.append(f"港股/美股暂无行情路由（{'/'.join(hk_us[:6])}），指标为空")

    return {
        "members": members, "stocks": stocks,
        "undisclosed": undisclosed, "effective_count": effective,
        "effective_min_weight": EFFECTIVE_MIN_WEIGHT, "over_limit": OVER_LIMIT,
        "max_lag_days": max_lag, "data_gaps": gaps,
    }
