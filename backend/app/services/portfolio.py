"""组合评估计算层（M3，实现方案 §4 POST /api/portfolio/eval）。

口径（与 §6 一致，界面标注）：
- 成员日收益 r_i(t) = (unit_i(t) + div_i(t)) / unit_i(t-1) - 1（现金分红口径）。
- 共同交易日对齐（QDII 滞后 1 天 → 非共同日整组剔除，§6-6 基准对齐同款）。
- 组合日收益 r_p(t) = Σ w_i·r_i(t)，**权重每日再平衡**（等权即均值）；
  合成净值从 1 起步累乘 → 复用 compute_metrics 出全套指标。
- 完整性闸门基金（110005 先例）：div 全序列不采信 → r 用纯单位净值比值，
  结果 gaps 显式标注「该成员收益略低估（分红未计）」，不阻断、不造假。
- 相关性：成员日收益两两按共同日对齐后取 pearson（样本 ≥20 才给值）。
- 基准超额：组合合成净值 vs 指数 close，align_common_dates 对齐后同窗
  window_return 相减；基准为价格指数（未含股息），界面标注。
"""
from __future__ import annotations

import math

from ..db import conn
from .metrics import (
    Series, align_common_dates, compute_metrics, has_negative_diff_drift,
    window_return,
)

BENCHMARK_NAMES = {"sh000300": "沪深300", "sh000852": "中证1000"}


def conn_read(sql: str, params: tuple) -> list:
    from ..db import conn
    with conn() as c:
        return c.execute(sql, params).fetchall()


def _member_daily_returns(m: dict, common_dates: list[str]) -> list[float]:
    """成员在共同日上的日收益（§6 现金分红口径；完整性闸门基金 div 置 0）。

    返回长度 = len(common_dates) - 1：第 k 项是共同日 k → k+1 的收益
    （首个共同日是基线，无收益；基线取成员自身首个共同日当日）。
    """
    idx = {d: i for i, d in enumerate(m["dates"])}
    div = m["div"] if m["integrity_ok"] else [0.0] * len(m["dates"])
    rets: list[float] = []
    prev_i: int | None = None
    for d in common_dates:
        i = idx.get(d)
        if i is None:
            continue
        if prev_i is not None:
            prev_unit = m["unit"][prev_i]
            if prev_unit and prev_unit > 0:
                rets.append((m["unit"][i] + div[i]) / prev_unit - 1)
        prev_i = i
    return rets


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _align_pair(a: dict, b: dict) -> tuple[list[float], list[float]]:
    """两成员日收益（相关矩阵用：两两共同交易日，比组合共同日更宽松）。"""
    dates = sorted(set(a["dates"]) & set(b["dates"]))
    rets_a = _member_daily_returns(a, dates)
    rets_b = _member_daily_returns(b, dates)
    n = min(len(rets_a), len(rets_b))
    return rets_a[:n], rets_b[:n]


def evaluate(codes: list[str], weights: dict[str, float] | None = None,
             benchmark: str | None = "sh000300",
             weight_mode: str = "manual") -> dict:
    """组合评估主入口。weights 已归一化；weight_mode 仅作结果标注。"""
    gaps: list[str] = []
    members_raw: dict[str, dict] = {}
    with conn() as c:
        for code in codes:
            rows = c.execute(
                "SELECT date, unit_nav, acc_nav, dividend FROM fund_nav"
                " WHERE code = ? ORDER BY date", (code,)).fetchall()
            if not rows:
                gaps.append(f"{code} 无净值数据（先刷新）")
                continue
            dates = [r["date"] for r in rows]
            unit = [r["unit_nav"] for r in rows]
            members_raw[code] = {
                "dates": dates, "unit": unit,
                "div": [r["dividend"] or 0.0 for r in rows],
                "integrity_ok": not has_negative_diff_drift(
                    [r["acc_nav"] for r in rows], unit),
            }
            if not members_raw[code]["integrity_ok"]:
                gaps.append(f"{code} 差值负向漂移：分红不采信，该成员收益略低估")
    usable = [code for code in codes if code in members_raw]
    if len(usable) < 1:
        return {"data_gaps": gaps or ["无可用成员"]}

    # 归一化权重（缺省等权）
    if weights:
        total = sum(max(0.0, weights.get(code, 0.0)) for code in usable)
        if total <= 0:
            weights = None
    if not weights:
        weights = {code: 1.0 / len(usable) for code in usable}
    else:
        weights = {code: max(0.0, weights.get(code, 0.0)) / total
                   for code in usable}

    common = set(members_raw[usable[0]]["dates"])
    for code in usable[1:]:
        common &= set(members_raw[code]["dates"])
    common_dates = sorted(common)
    if len(common_dates) < 2:
        gaps.append("共同交易日不足 2 天，无法合成")
        return {"data_gaps": gaps}

    # 组合日收益 → 合成净值（每日再平衡；首个共同日为基线 nav=1）
    per_member_rets = {code: _member_daily_returns(members_raw[code], common_dates)
                       for code in usable}
    nav = [1.0]
    for t in range(1, len(common_dates)):
        r_p = 0.0
        for code in usable:
            rets = per_member_rets[code]
            r_p += weights[code] * (rets[t - 1] if t - 1 < len(rets) else 0.0)
        nav.append(nav[-1] * (1 + r_p))
    portfolio_metric = compute_metrics(Series(common_dates, nav))

    # 相关矩阵（两两共同日）
    corr_codes = usable
    corr = [[None] * len(corr_codes) for _ in corr_codes]
    for i, ca in enumerate(corr_codes):
        corr[i][i] = 1.0
        for j in range(i + 1, len(corr_codes)):
            ra, rb = _align_pair(members_raw[ca], members_raw[corr_codes[j]])
            v = _pearson(ra, rb)
            corr[i][j] = corr[j][i] = v

    # 基准对齐 + 超额
    bench_nav: list[float] = []
    excess: dict[str, float | None] = {}
    bench_name = BENCHMARK_NAMES.get(benchmark or "", benchmark)
    if benchmark:
        rows = conn_read("SELECT date, close FROM index_daily WHERE code = ? ORDER BY date",
                         (benchmark,))
        if not rows:
            gaps.append(f"基准 {bench_name}（{benchmark}）未入库（POST /api/refresh?scope=index）")
        else:
            aligned_d, p_vals, b_vals = align_common_dates(
                common_dates, nav, [r["date"] for r in rows], [r["close"] for r in rows])
            if len(p_vals) < 2:
                gaps.append("组合与基准共同交易日不足，超额未算")
            else:
                bench_nav = [v / b_vals[0] for v in b_vals]  # 归一到 1 起步便于同图
                # §6-6 铁律：超额必须在共同日对齐后的序列上算（错位会虚增/虚减 2pp 量级）
                p_series = Series(aligned_d, p_vals)
                b_series = Series(aligned_d, b_vals)
                as_of = aligned_d[-1]
                from .metrics import _shift  # noqa: PLC2701 同包内部口径函数

                def _ex(months: int | None, ytd: bool = False, one_year: bool = False) -> float | None:
                    if ytd:
                        start = _shift(f"{as_of[:4]}-01-01", -1)
                    elif one_year:
                        start = _shift(as_of, -365)
                    else:
                        start = _shift(as_of, -30 * months)
                    rf, rb_ = window_return(p_series, start), window_return(b_series, start)
                    return None if rf is None or rb_ is None else rf - rb_

                excess = {"ret_1m": _ex(1), "ret_3m": _ex(3), "ret_6m": _ex(6),
                          "ret_ytd": _ex(None, ytd=True), "ret_1y": _ex(None, one_year=True)}

    return {
        "codes": usable, "weights_used": weights, "weight_mode": weight_mode,
        "benchmark": benchmark, "benchmark_name": bench_name if benchmark else None,
        "portfolio_metric": portfolio_metric,
        "nav_dates": common_dates, "portfolio_nav": nav,
        "benchmark_nav": bench_nav, "excess": excess,
        "corr_codes": corr_codes, "corr_matrix": corr,
        "data_gaps": gaps,
    }


def default_weights_from_positions(codes: list[str]) -> dict[str, float] | None:
    """M3 默认权重：my_position 份额×最新净值 占比。任一代码缺 position → None。"""
    values: dict[str, float] = {}
    with conn() as c:
        for code in codes:
            pos = c.execute("SELECT shares FROM my_position WHERE code = ?",
                            (code,)).fetchone()
            last = c.execute(
                "SELECT unit_nav FROM fund_nav WHERE code = ? ORDER BY date DESC LIMIT 1",
                (code,)).fetchone()
            if not pos or not pos["shares"] or not last:
                return None
            values[code] = pos["shares"] * last["unit_nav"]
    total = sum(values.values())
    return {code: v / total for code, v in values.items()} if total > 0 else None
