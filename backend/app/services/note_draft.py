"""结论自动草稿（M3）：从库内数据确定性生成 markdown 模板。

设计约定（HANDOFF 2026-10-28 用户确认）：**不用 LLM 生成底稿**——用户无量化
基础，草稿必须可复算、可核对。这里只做「库内有什么就摆什么」的模板拼装：
指标 + 持仓环比 + 分红 + 缺口 + 规则化提示，末尾留人工结论空位。
前端拿到后填入编辑框，**不自动保存**（用户修订后手动保存才落库）。
"""
from __future__ import annotations

from datetime import date, datetime

from ..db import conn


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:+.2f}%"


def _holdings_diff(code: str) -> tuple[str, list[str]]:
    """最新两期前十大持仓环比：新进/退出/加仓/减仓。返回 (最新报告期, 摘要行)。"""
    with conn() as c:
        rows = c.execute(
            "SELECT report_date, stock_name, weight FROM fund_holding"
            " WHERE code = ? ORDER BY report_date DESC", (code,)).fetchall()
    if not rows:
        return "", []
    periods = sorted({r["report_date"] for r in rows}, reverse=True)
    latest = [r for r in rows if r["report_date"] == periods[0]]
    if len(periods) < 2:
        return periods[0], [f"库内仅一期报告（{periods[0]}），环比待下一期披露"]
    prev = {r["stock_name"]: r["weight"] for r in rows if r["report_date"] == periods[1]}
    lines = []
    for r in latest:
        name, w = r["stock_name"], r["weight"]
        if name not in prev:
            lines.append(f"- 新进：{name}（{w:.2f}%）")
        elif w - prev[name] > 0.5:
            lines.append(f"- 加仓：{name} {prev[name]:.2f}% → {w:.2f}%")
        elif prev[name] - w > 0.5:
            lines.append(f"- 减仓：{name} {prev[name]:.2f}% → {w:.2f}%")
    prev_names = set(prev) - {r["stock_name"] for r in latest}
    lines += [f"- 退出：{n}（上期 {prev[n]:.2f}%）" for n in sorted(prev_names)]
    if not lines:
        lines.append("- 前十大名单与权重基本未变（变动 <0.5pp）")
    return periods[0], lines


def build_note_draft(code: str) -> str:
    today = date.today().isoformat()
    with conn() as c:
        fund = c.execute("SELECT * FROM fund WHERE code = ?", (code,)).fetchone()
        if not fund:
            raise KeyError(f"基金 {code} 不在池中")
        profile = c.execute(
            "SELECT * FROM fund_profile WHERE code = ? ORDER BY as_of DESC LIMIT 1",
            (code,)).fetchone()
        metric = c.execute(
            "SELECT * FROM fund_metric WHERE code = ? ORDER BY as_of DESC LIMIT 1",
            (code,)).fetchone()
        nav_rows = c.execute(
            "SELECT date, dividend, unit_nav FROM fund_nav WHERE code = ? ORDER BY date",
            (code,)).fetchall()
        position = c.execute(
            "SELECT * FROM my_position WHERE code = ?", (code,)).fetchone()

    from ..services.metrics import has_negative_diff_drift  # noqa: F401 完整性闸门经 _collect_gaps 生效
    from ..routers.funds import _collect_gaps  # 复用详情页缺口口径，不另造一套

    gaps, _integrity = _collect_gaps(code)

    p = dict(profile) if profile else {}
    m = dict(metric) if metric else None

    # 近 1 年分红事件
    year_ago = f"{int(today[:4]) - 1}{today[4:]}"
    dividends = [(r["date"], r["dividend"]) for r in nav_rows
                 if r["dividend"] and r["dividend"] > 0 and r["date"] >= year_ago]
    div_lines = [f"- {d}：每份 {v:.4f} 元" for d, v in dividends] or ["- 近 1 年无分红记录"]

    latest_period, diff_lines = _holdings_diff(code)
    lag_days = ((datetime.today() - datetime.strptime(latest_period, "%Y-%m-%d")).days
                if latest_period else None)

    # 规则化提示（阈值明示，可复算）
    hints = []
    if m:
        if m.get("max_dd") is not None and m["max_dd"] < -0.20:
            hints.append(f"近 1 年最大回撤 {_pct(m['max_dd'])}，超 -20% 阈值")
        if m.get("sharpe") is not None and m["sharpe"] < 0:
            hints.append(f"近 1 年夏普 {m['sharpe']:.2f} < 0（波动未换来收益）")
        if m.get("ret_1y") is not None and m["ret_1y"] < -0.10:
            hints.append(f"近 1 年收益 {_pct(m['ret_1y'])}，深负区间")
    if lag_days is not None and lag_days > 120:
        hints.append(f"持仓报告期已滞后 {lag_days} 天，环比信息陈旧")
    if not hints:
        hints.append("无触发的规则提示（回撤 -20% / 夏普 0 / 收益 -10% / 滞后 120 天均未越线）")

    pos_line = ""
    if position and position["shares"]:
        last = nav_rows[-1] if nav_rows else None  # 实时口径：份额 × 最新单位净值
        if last:
            pos_line = (f"\n## 持仓\n- 份额 {position['shares']:,.2f}，市值 "
                        f"{position['shares'] * last['unit_nav']:,.0f} 元"
                        f" @ 最新净值 {last['date']}\n")
        else:
            pos_line = f"\n## 持仓\n- 份额 {position['shares']:,.2f}，净值未入库，市值待算\n"

    name = fund["name"] or p.get("name") or code
    lines = [
        f"# {name}（{code}）结论草稿",
        f"> 自动模板生成于 {today}（库内确定性数据拼装，非 LLM）；请修订后手动保存，不自动落库。",
        "",
        "## 基本面",
        f"- 类型：{p.get('fund_type') or '—'}；规模：{p.get('scale') or '—'}",
        f"- 经理：{p.get('manager') or '—'}（{p.get('company') or '—'}）",
        f"- 成立：{p.get('inception_date') or '—'}"
        + (f"；跟踪：{p['tracked_index']}" if p.get("tracked_index") else ""),
        "",
        "## 指标（§6 口径：现金分红收益 / 自算年化 / √252 波动 / 2% 无风险夏普）",
    ]
    if m:
        lines += [
            f"- YTD {_pct(m.get('ret_ytd'))}｜近1年 {_pct(m.get('ret_1y'))}"
            f"｜年化(1y) {_pct(m.get('ann_ret'))}（净值截至 {m.get('as_of')}）",
            f"- 最大回撤(1y) {_pct(m.get('max_dd'))}｜年化波动(1y) "
            f"{_pct(m.get('ann_vol'))}｜夏普(1y) "
            + ("—" if m.get("sharpe") is None else f"{m['sharpe']:.2f}"),
        ]
    else:
        lines.append("- 指标未计算（完整性闸门或净值不足），见下方数据缺口")
    lines += [
        "",
        f"## 持仓环比（{latest_period or '无报告期'}）",
        *diff_lines,
        "",
        "## 分红（近 1 年）",
        *div_lines,
    ]
    if pos_line:
        lines.append(pos_line.rstrip())
    lines += [
        "",
        "## 数据缺口",
        *([f"- {g}" for g in gaps] or ["- 无"]),
        "",
        "## 规则提示（阈值见草稿生成逻辑）",
        *(f"- {h}" for h in hints),
        "",
        "## 人工结论（待填）",
        "- 核心判断：",
        "- 操作：",
        "",
    ]
    return "\n".join(lines)
