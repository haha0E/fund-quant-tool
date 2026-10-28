"""画像库接口：入池/列表/详情/标签/结论层（FR1）。

结论层双层结构（实现方案 §1）：note 写 SQLite 的同时导出 md 快照到 data/notes/，
保证仓库里永远有一份人可读、可 git diff 的结论。
"""
from fastapi import APIRouter, HTTPException

from ..config import NOTES_DIR
from ..db import conn
from ..schemas import (
    FundIn, FundOut, FundPatch, NoteIn, NoteOut, FundDetailOut,
    MetricOut, NavPoint, DividendEvent, HoldingOut,
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

    # 完整性闸门：差值负向漂移（110005 份额折算先例）→ 指标不采信，缺口显式标注
    integrity_bad = has_negative_diff_drift([r["acc_nav"] for r in nav_rows],
                                            [r["unit_nav"] for r in nav_rows])
    if integrity_bad:
        metric_out = None
        gaps.append("净值差值序列负向漂移（份额折算/数据修正），指标不采信——复查报告 2026-10-20 §四定调")
    else:
        metric_out = MetricOut(**dict(metric)) if metric else None
        if not metric and nav_rows:
            gaps.append("指标未计算（POST /api/refresh?scope=metrics）")

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
        data_gaps=gaps,
    )
    if not detail.holdings:
        detail.data_gaps.append("前十大持仓未披露或未摄取（QDII/新基金常滞后）")
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
