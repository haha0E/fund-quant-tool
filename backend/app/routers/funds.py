"""画像库接口：入池/列表/详情/标签/结论层（FR1）+ 持仓录入/预检/草稿（M3）。

结论层双层结构（实现方案 §1）：note 写 SQLite 的同时导出 md 快照到 data/notes/，
保证仓库里永远有一份人可读、可 git diff 的结论。
"""
from fastapi import APIRouter, HTTPException

from ..config import NOTES_DIR
from ..db import conn
from ..schemas import (
    FundIn, FundOut, FundPatch, NoteIn, NoteOut, FundDetailOut,
    MetricOut, NavPoint, DividendEvent, HoldingOut,
    PositionIn, PositionOut, PreflightOut, NoteDraftOut,
)
from ..services.metrics import has_negative_diff_drift

router = APIRouter(prefix="/api/funds", tags=["funds"])


def _tags_to_str(tags: list[str]) -> str:
    return ",".join(t.strip() for t in tags if t.strip())


def _row_to_fund(row) -> FundOut:
    return FundOut(
        code=row["code"],
        name=row["name"],
        pool_type=row["pool_type"],
        domain_tags=[t for t in row["domain_tags"].split(",") if t],
        created_at=row["created_at"],
        has_note=bool(row["has_note"]),
    )


_LIST_SQL = """
SELECT f.code, f.name, f.pool_type, f.domain_tags, f.created_at,
       EXISTS(SELECT 1 FROM note n WHERE n.fund_code = f.code) AS has_note
FROM fund f
"""


def _collect_gaps(code: str) -> tuple[list[str], bool]:
    """数据缺口清单 + 完整性闸门标记（详情页与结论草稿共用同一口径）。

    缺口显式标注不静默造假（红线）；完整性闸门（110005 差值负向漂移先例）
    命中时指标不采信，由调用方置 metric=None。
    """
    with conn() as c:
        profile = c.execute(
            "SELECT * FROM fund_profile WHERE code = ? ORDER BY as_of DESC LIMIT 1",
            (code,)).fetchone()
        metric = c.execute(
            "SELECT 1 FROM fund_metric WHERE code = ? LIMIT 1", (code,)).fetchone()
        nav_rows = c.execute(
            "SELECT date, unit_nav, acc_nav, dividend FROM fund_nav"
            " WHERE code = ? ORDER BY date", (code,)).fetchall()
        holding_n = c.execute(
            "SELECT COUNT(DISTINCT report_date) AS n FROM fund_holding WHERE code = ?",
            (code,)).fetchone()["n"]

    gaps: list[str] = []
    profile_dict = dict(profile) if profile else None
    if profile_dict:
        for f in ("fee_management", "fee_custody", "fee_subscription", "fee_redemption",
                  "stock_position", "manager", "benchmark", "scale"):
            if profile_dict.get(f) is None:
                gaps.append(f"档案缺 {f}")
    else:
        gaps.append("档案未摄取（POST /api/refresh?scope=profile）")
    if not nav_rows:
        gaps.append("净值未摄取（POST /api/refresh?scope=nav）")
    if not holding_n:
        gaps.append("前十大持仓未披露或未摄取（QDII/新基金常滞后）")

    integrity_bad = has_negative_diff_drift([r["acc_nav"] for r in nav_rows],
                                            [r["unit_nav"] for r in nav_rows])
    if integrity_bad:
        gaps.append("净值差值序列负向漂移（份额折算/数据修正），指标不采信——复查报告 2026-10-20 §四定调")
    elif not metric and nav_rows:
        gaps.append("指标未计算（POST /api/refresh?scope=metrics）")
    return gaps, integrity_bad


@router.get("", response_model=list[FundOut])
def list_funds(pool: str | None = None):
    sql, params = _LIST_SQL, []
    if pool:
        sql += " WHERE f.pool_type = ?"
        params.append(pool)
    sql += " ORDER BY f.pool_type, f.code"
    with conn() as c:
        return [_row_to_fund(r) for r in c.execute(sql, params)]


@router.get("/{code}", response_model=FundDetailOut)
def fund_detail(code: str):
    """单基金画像（FR1/故事4）：档案 20 字段 + 指标 + 最新前十持仓 + 净值 + 结论。

    数据缺口显式列入 data_gaps（未摄取/未披露的字段点名），不静默造假。
    """
    with conn() as c:
        fund = c.execute("SELECT * FROM fund WHERE code = ?", (code,)).fetchone()
        if not fund:
            raise HTTPException(404, f"基金 {code} 不存在")
        profile = c.execute(
            "SELECT * FROM fund_profile WHERE code = ? ORDER BY as_of DESC LIMIT 1",
            (code,)).fetchone()
        metric = c.execute(
            "SELECT * FROM fund_metric WHERE code = ? ORDER BY as_of DESC LIMIT 1",
            (code,)).fetchone()
        nav_rows = c.execute(
            "SELECT date, unit_nav, acc_nav, dividend FROM fund_nav"
            " WHERE code = ? ORDER BY date", (code,)).fetchall()
        holding_rows = c.execute(
            "SELECT * FROM fund_holding WHERE code = ? ORDER BY report_date DESC",
            (code,)).fetchall()
        note = c.execute("SELECT * FROM note WHERE fund_code = ?", (code,)).fetchone()
        position = c.execute(
            "SELECT * FROM my_position WHERE code = ?", (code,)).fetchone()

    # 持仓市值实时口径：份额 × 最新单位净值（库内 my_position 快照仅作录入审计）
    position_out = None
    if position:
        last_nav = nav_rows[-1] if nav_rows else None
        position_out = PositionOut(
            code=position["code"], shares=position["shares"],
            market_value=round(position["shares"] * last_nav["unit_nav"], 2)
                if position["shares"] and last_nav else None,
            value_as_of=last_nav["date"]
                if position["shares"] and last_nav else None,
            updated_at=position["updated_at"])

    gaps, integrity_bad = _collect_gaps(code)
    profile_dict = dict(profile) if profile else None
    metric_out = None
    if not integrity_bad:
        metric_out = MetricOut(**dict(metric)) if metric else None

    periods = sorted({r["report_date"] for r in holding_rows}, reverse=True)
    latest_holdings = [r for r in holding_rows if r["report_date"] == periods[0]] \
        if periods else []

    detail = FundDetailOut(
        code=fund["code"], name=fund["name"], pool_type=fund["pool_type"],
        domain_tags=[t for t in fund["domain_tags"].split(",") if t],
        profile=profile_dict, metric=metric_out,
        nav=[NavPoint(**dict(r)) for r in nav_rows],
        dividends=[DividendEvent(date=r["date"], dividend=r["dividend"])
                   for r in nav_rows if r["dividend"] and r["dividend"] > 0],
        holdings=[HoldingOut(**{k: r[k] for k in
                                ("report_date", "stock_code", "stock_name", "weight")})
                  for r in latest_holdings],
        holding_periods=periods,
        note=note["content"] if note else "",
        note_updated_at=note["updated_at"] if note else None,
        position=position_out,
        data_gaps=gaps,
    )
    return detail


@router.post("", response_model=FundOut, status_code=201)
def add_fund(fund: FundIn):
    with conn() as c:
        exists = c.execute("SELECT 1 FROM fund WHERE code = ?", (fund.code,)).fetchone()
        if exists:
            raise HTTPException(409, f"基金 {fund.code} 已在池中")
        c.execute(
            "INSERT INTO fund (code, name, pool_type, domain_tags) VALUES (?, ?, ?, ?)",
            (fund.code, fund.name, fund.pool_type, _tags_to_str(fund.domain_tags)),
        )
        row = c.execute(
            _LIST_SQL + " WHERE f.code = ?", (fund.code,)
        ).fetchone()
        return _row_to_fund(row)


@router.patch("/{code}", response_model=FundOut)
def update_fund(code: str, patch: FundPatch):
    with conn() as c:
        row = c.execute("SELECT * FROM fund WHERE code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, f"基金 {code} 不存在")
        if patch.name is not None:
            c.execute("UPDATE fund SET name = ? WHERE code = ?", (patch.name, code))
        if patch.pool_type is not None:
            c.execute("UPDATE fund SET pool_type = ? WHERE code = ?", (patch.pool_type, code))
        if patch.domain_tags is not None:
            c.execute("UPDATE fund SET domain_tags = ? WHERE code = ?",
                      (_tags_to_str(patch.domain_tags), code))
        row = c.execute(_LIST_SQL + " WHERE f.code = ?", (code,)).fetchone()
        return _row_to_fund(row)


@router.delete("/{code}", status_code=204)
def remove_fund(code: str):
    with conn() as c:
        cur = c.execute("DELETE FROM fund WHERE code = ?", (code,))
        if cur.rowcount == 0:
            raise HTTPException(404, f"基金 {code} 不存在")


@router.get("/{code}/note", response_model=NoteOut)
def get_note(code: str):
    with conn() as c:
        row = c.execute("SELECT * FROM note WHERE fund_code = ?", (code,)).fetchone()
        if not row:
            raise HTTPException(404, f"基金 {code} 还没有结论笔记")
        return NoteOut(**dict(row))


# ---- M3：预检入池 / 持仓录入 / 结论草稿 ----

# 领域标签推断（保守规则：宁缺毋滥，匹配不上返回空让用户手选；可核对非 LLM）
# 词表按池内 12 只真实标签反推校验：022364 科技智选推不出（不把"科技"当算力），
# 161725 白酒→消费、020972 机器人、021030 创新药→医药、004195 中证1000→宽基、012920 QDII。
_TAG_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("医药", ("医药", "创新药", "医疗", "生物医", "健康")),
    ("机器人", ("机器人",)),
    ("AI算力", ("算力", "人工智能", "半导体", "芯片", "集成电路", "计算机", "光模块")),
    ("黄金", ("黄金", "贵金属")),
    ("红利", ("红利", "股息")),
    ("消费", ("消费", "白酒", "食品饮料")),
]
_BROAD_INDEXES = ("沪深300", "中证500", "中证800", "中证1000", "中证A500",
                  "上证50", "创业板", "科创50", "中证全指", "MSCI中国A50")


def _suggest_tags(name: str, fund_type: str | None,
                  tracked_index: str | None, benchmark: str | None) -> list[str]:
    hay = f"{name} {tracked_index or ''} {benchmark or ''}"
    tags = [tag for tag, words in _TAG_RULES if any(w in hay for w in words)]
    # 宽基只对指数型判（主动型基金的基准常含宽基指数做参照，不等于它是宽基）
    if "指数" in (fund_type or "") and any(ix in hay for ix in _BROAD_INDEXES):
        tags.append("宽基")
    if ("QDII" in (fund_type or "").upper()) or any(
            w in f"{name} {fund_type or ''}" for w in ("QDII", "全球精选", "海外", "美国")):
        tags.append("QDII")
    return tags


@router.get("/preflight/{code}", response_model=PreflightOut)
def preflight(code: str):
    """预检入池（M3）：走 ingest 拉档案+净值算预览，**不入库不写池**。

    外呼受反爬限速（0.6s 间隔+指数退避+当日缓存），实测约 2-4 秒；
    预览收益走 §6 现金分红口径（分红由差值变动现推，完整性闸门同款）。
    """
    from ..ingest import source_map
    from ..ingest.refresh import _detect_dividends
    from ..services.metrics import Series, window_return

    if len(code) != 6 or not code.isdigit():
        raise HTTPException(400, "基金代码须为 6 位数字")
    try:
        basic = source_map.fetch("profile_basic", code=code)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"档案预检失败（代码可能有误或数据源异常）：{e}") from e
    try:
        rows = _detect_dividends(source_map.fetch("nav", code=code))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"净值预检失败：{e}") from e

    warnings: list[str] = []
    name = basic.get("基金名称") or ""
    if not name:
        warnings.append("名录未返回基金名称，请人工确认代码")
    integrity_bad = any(r["anomaly"] for r in rows)
    ret_1y = ret_ytd = None
    if len(rows) >= 2 and rows[-1]["date"] >= rows[0]["date"]:
        s = Series([r["date"] for r in rows], [r["unit_nav"] for r in rows],
                   [r["dividend"] for r in rows])
        as_of = rows[-1]["date"]
        ret_1y = window_return(s, _shift(as_of, -365))
        ret_ytd = window_return(s, _shift(f"{as_of[:4]}-01-01", -1))
    if integrity_bad:
        warnings.append("差值负向漂移（份额折算先例）：预览收益按无分红口径，略低估")
    return PreflightOut(
        code=code, name=name,
        fund_type=basic.get("基金类型"), company=basic.get("基金公司"),
        manager=basic.get("基金经理"), scale=basic.get("最新规模"),
        inception_date=basic.get("成立时间"),
        latest_nav_date=rows[-1]["date"] if rows else None,
        ret_1y=ret_1y, ret_ytd=ret_ytd, integrity_bad=integrity_bad,
        warnings=warnings,
        suggested_tags=_suggest_tags(name, basic.get("基金类型"),
                                     basic.get("跟踪标的"), basic.get("业绩比较基准")),
    )


@router.put("/{code}/position", response_model=PositionOut)
def save_position(code: str, pos: PositionIn):
    """持仓份额录入（M3）。份额是唯一事实源；市值显示口径 = 份额 × 最新单位净值
    （实时算，见详情/仪表盘），此处存的快照仅作录入时点审计记录，不再用于显示。"""
    with conn() as c:
        if not c.execute("SELECT 1 FROM fund WHERE code = ?", (code,)).fetchone():
            raise HTTPException(404, f"基金 {code} 不在池中")
        last = c.execute(
            "SELECT date, unit_nav FROM fund_nav WHERE code = ? ORDER BY date DESC LIMIT 1",
            (code,)).fetchone()
        market_value = round(pos.shares * last["unit_nav"], 2) if last else None
        value_as_of = last["date"] if last else None
        c.execute(
            """INSERT INTO my_position (code, shares, market_value, value_as_of, updated_at)
               VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
               ON CONFLICT(code) DO UPDATE SET
                   shares = excluded.shares, market_value = excluded.market_value,
                   value_as_of = excluded.value_as_of, updated_at = excluded.updated_at""",
            (code, pos.shares, market_value, value_as_of))
        row = c.execute("SELECT * FROM my_position WHERE code = ?", (code,)).fetchone()
    return PositionOut(**dict(row))


@router.delete("/{code}/position", status_code=204)
def clear_position(code: str):
    with conn() as c:
        cur = c.execute("DELETE FROM my_position WHERE code = ?", (code,))
        if cur.rowcount == 0:
            raise HTTPException(404, f"基金 {code} 没有持仓记录")


@router.get("/{code}/note/draft", response_model=NoteDraftOut)
def note_draft(code: str):
    """结论自动草稿（M3）：库内确定性模板（指标+持仓环比+分红+缺口+规则提示）。

    不用 LLM——可复算可信；前端填入编辑框，**不自动保存**。
    """
    from ..services.note_draft import build_note_draft
    try:
        return NoteDraftOut(draft=build_note_draft(code))
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


def _shift(date_str: str, days: int) -> str:
    from datetime import datetime, timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return d.strftime("%Y-%m-%d")


@router.put("/{code}/note", response_model=NoteOut)
def save_note(code: str, note: NoteIn):
    with conn() as c:
        if not c.execute("SELECT 1 FROM fund WHERE code = ?", (code,)).fetchone():
            raise HTTPException(404, f"基金 {code} 不存在")
        c.execute(
            """INSERT INTO note (fund_code, content, updated_at)
               VALUES (?, ?, datetime('now', 'localtime'))
               ON CONFLICT(fund_code) DO UPDATE
               SET content = excluded.content,
                   updated_at = excluded.updated_at""",
            (code, note.content),
        )
        row = c.execute("SELECT * FROM note WHERE fund_code = ?", (code,)).fetchone()

    # 结论层双写：md 快照（显式 utf-8，Windows 纪律）
    (NOTES_DIR / f"{code}.md").write_text(note.content, encoding="utf-8")
    return NoteOut(**dict(row))
