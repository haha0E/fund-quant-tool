"""计算层纯函数：区间收益 / 年化 / 最大回撤 / 年化波动 / 夏普（实现方案 §6 口径）。

口径强制（2026-10-20 复查反转教训，写入代码注释与界面 tooltip，两边文案保持一致）：

1. 区间收益率
   - 窗内无分红：unit_nav(t1)/unit_nav(t0) - 1（精确）。
   - 窗内有分红：(unit_nav(t1) + 窗内分红现金合计) / unit_nav(t0) - 1（现金口径，分红不再投）。
   - **禁止用累计净值算区间收益**——历史分红常数会阻尼失真
     （000390 实测：常数 3.078 把真实 -29.6% 阻尼成 -13.9%）。
2. 年化收益：自算 (1+R)^(365/天数) - 1，不用任何数据商「年化」列。
3. 最大回撤：单位净值 running max 取 min(nav/cummax(nav)-1)；
   窗内含分红日时先按「单位 + 窗内累计分红」重构序列再取。
4. 年化波动率：日收益 std × sqrt(252)；分红日日收益 = (unit+div)/prev_unit - 1；
   QDII 用可得交易日，不强补。
5. 夏普：(年化收益 - 2%) / 年化波动，无风险利率固定 2% 并标注。
6. 基准对齐：基金与基准先按共同交易日对齐再算超额（004195/012920 净值滞后
   1 天，直接错位对比会虚增/虚减超额 2pp 量级）。

约定：输入序列为等长 list，dates 升序，unit/div 可为 float|None（None 表示
该日缺失，函数内部成对剔除）。所有收益率以小数返回（0.01 = 1%）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

RISK_FREE = 0.02  # 夏普无风险利率，固定 2%（§6：固定并标注）


def has_negative_diff_drift(acc_nav: list[float | None], unit_nav: list[float]) -> bool:
    """数据完整性闸门：累计-单位差值出现负向变动 → 全序列不采信。

    110005 先例（2026-10-28 实测）：份额折算/数据修正后差值序列日间振荡，
    正向跳动会被误判成分红（振荡累出 5 元假分红、1 年收益虚到 +657%）。
    差值只作分红核对常数；一旦完整性破坏，分红推断与指标整段不作数，
    界面按数据缺口显式标注（复查报告 2026-10-20 §四定调：不采信）。
    """
    prev: float | None = None
    for a, u in zip(acc_nav, unit_nav):
        if a is None or u is None:
            continue
        d = a - u
        if prev is not None and d < prev - 1e-9:
            return True
        prev = d
    return False

# 界面 tooltip 文案（前端 FundDetail 与此处保持同义）
TOOLTIPS = {
    "ret": "区间收益率：窗内无分红=单位净值比值；窗内有分红=(期末单位净值+窗内分红现金)/期初单位净值。禁止用累计净值（历史分红常数会阻尼失真）。",
    "ann_ret": "年化收益：自算 (1+区间收益)^(365/天数)-1，不采用数据商年化列。",
    "max_dd": "最大回撤：单位净值 running max 取最深跌幅；窗内含分红日先按「单位+窗内累计分红」重构。",
    "ann_vol": "年化波动率：日收益标准差×√252；分红日按含现金口径计日收益；QDII 用可得交易日。",
    "sharpe": "夏普：(年化收益-无风险2%)/年化波动。无风险利率固定 2%。",
}


@dataclass
class Series:
    """净值序列 + 每日分红（dividend 默认全 0）。"""
    dates: list[str]
    unit: list[float]
    div: list[float] | None = None


def _clean(series: Series) -> tuple[list[str], list[float], list[float]]:
    """成对剔除 None/NaN，返回 (dates, unit, div)。"""
    div = series.div or [0.0] * len(series.dates)
    out_d, out_u, out_v = [], [], []
    for d, u, v in zip(series.dates, series.unit, div):
        if u is None or math.isnan(u):
            continue
        out_d.append(d)
        out_u.append(float(u))
        out_v.append(float(v or 0.0))
    return out_d, out_u, out_v


def _find_idx(dates: list[str], boundary: str, side: str = "le") -> int | None:
    """找 <=（le）或 <（lt）boundary 的最后一个下标。"""
    idx = None
    for i, d in enumerate(dates):
        if (side == "le" and d <= boundary) or (side == "lt" and d < boundary):
            idx = i
        else:
            break
    return idx


def window_return(series: Series, start: str, end: str | None = None) -> float | None:
    """区间收益率（§6-1 现金分红口径）。

    start/end 为日历日字符串；实际基线取 start 前最后一个净值日
    （start 当日有净值则含当日，分红窗口为 (基线日, 截止日]）。
    """
    dates, unit, div = _clean(series)
    if not dates:
        return None
    end = end or dates[-1]
    i1 = _find_idx(dates, end, "le")
    if i1 is None:
        return None
    i0 = _find_idx(dates, start, "le")
    if i0 is None:  # 序列晚于窗口起点（如新基金）→ 基线取首个净值日
        i0 = 0
    if i1 <= i0:
        return None
    cash = sum(div[i0 + 1 : i1 + 1])  # 窗内分红现金（现金口径，不再投）
    return (unit[i1] + cash) / unit[i0] - 1


def reconstruct_window(series: Series, start: str) -> tuple[list[str], list[float]]:
    """窗内序列重构（§6-3）：单位 + 窗内累计分红。最大回撤/图表专用。"""
    dates, unit, div = _clean(series)
    i0 = _find_idx(dates, start, "le")
    if i0 is None:
        i0 = 0
    out_d, out_u, cum = [], [], 0.0
    for i in range(i0, len(dates)):
        cum += div[i]
        out_d.append(dates[i])
        out_u.append(unit[i] + cum)
    return out_d, out_u


def max_drawdown(dates: list[str], values: list[float]) -> float | None:
    """running max 最深跌幅（输入应已按窗重构）。返回负小数或 0。"""
    if len(values) < 2:
        return None
    peak = -math.inf
    mdd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1)
    return mdd


def daily_returns(series: Series) -> list[float]:
    """日收益序列（§6-4）：分红日 r=(unit+div)/prev_unit-1。"""
    _, unit, div = _clean(series)
    rets = []
    for i in range(1, len(unit)):
        prev = unit[i - 1]
        if prev > 0:
            rets.append((unit[i] + div[i]) / prev - 1)
    return rets


def ann_volatility(series: Series) -> float | None:
    rets = daily_returns(series)
    if len(rets) < 20:  # 样本太少不给波动率
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def annualized_return(r: float, days: int) -> float | None:
    """§6-2 自算年化：(1+R)^(365/days)-1。days 为日历天。"""
    if r is None or days <= 0 or r <= -1:
        return None
    return (1 + r) ** (365 / days) - 1


def sharpe(ann_ret: float | None, vol: float | None) -> float | None:
    if ann_ret is None or vol is None or vol == 0:
        return None
    return (ann_ret - RISK_FREE) / vol


def _shift(date_str: str, days: int) -> str:
    """日历日平移（无第三方依赖）。"""
    from datetime import datetime, timedelta

    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


def compute_metrics(series: Series, as_of: str | None = None) -> dict:
    """画像页指标表全量计算（落 fund_metric 的口径）。

    ann_ret/max_dd/ann_vol/sharpe 均取近 1 年窗口（不足 1 年取全部历史），
    tooltip 明示；ret_* 为各自窗口的现金分红口径区间收益。
    """
    dates, unit, _ = _clean(series)
    if len(dates) < 2:
        return {"as_of": dates[0] if dates else None}
    as_of = as_of or dates[-1]
    year_start = f"{as_of[:4]}-01-01"

    def ret(months: int | None, ytd: bool = False, one_year: bool = False) -> float | None:
        if ytd:
            return window_return(series, _shift(year_start, -1))
        if one_year:
            return window_return(series, _shift(as_of, -365))
        return window_return(series, _shift(as_of, -30 * months))

    ret_1y = ret(None, one_year=True)
    # 近 1 年窗口（序列不足则全历史）
    win_start = _shift(as_of, -365)
    i_base = _find_idx(dates, win_start, "le")
    if i_base is None:
        i_base = 0
        win_start = dates[0]
    adj_dates, adj_vals = reconstruct_window(series, win_start)
    mdd = max_drawdown(adj_dates, adj_vals)
    # 波动率用原始单位净值+分红列的近 1 年切片（分红日按现金口径计日收益）
    div_all = series.div[i_base:] if series.div else None
    vol = ann_volatility(Series(dates[i_base:], unit[i_base:], div_all))
    a_ret = None
    if ret_1y is not None:
        from datetime import datetime
        days = (datetime.strptime(as_of, "%Y-%m-%d")
                - datetime.strptime(dates[i_base], "%Y-%m-%d")).days
        a_ret = annualized_return(ret_1y, days)
    return {
        "as_of": as_of,
        "ret_1m": ret(1),
        "ret_3m": ret(3),
        "ret_6m": ret(6),
        "ret_ytd": ret(None, ytd=True),
        "ret_1y": ret_1y,
        "ann_ret": a_ret,
        "max_dd": mdd,
        "ann_vol": vol,
        "sharpe": sharpe(a_ret, vol),
    }


# ---- 基准对齐（§6-6；M3 组合评估复用，M2 回归用例覆盖） ----

def align_common_dates(dates_a: list[str], vals_a: list[float],
                       dates_b: list[str], vals_b: list[float]) -> tuple[list[str], list[float], list[float]]:
    """按共同交易日对齐两条序列（保留双方都有数据的日期，升序）。"""
    map_b = dict(zip(dates_b, vals_b))
    out_d, out_a, out_b = [], [], []
    for d, v in zip(dates_a, vals_a):
        if d in map_b:
            out_d.append(d)
            out_a.append(v)
            out_b.append(map_b[d])
    return out_d, out_a, out_b


def excess_return(ret_fund: float, ret_bench: float) -> float:
    """基准超额 = 基金区间收益 - 基准区间收益（对齐后同窗相减）。"""
    return ret_fund - ret_bench
