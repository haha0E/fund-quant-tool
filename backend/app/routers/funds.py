"""画像库接口：入池/列表/详情/标签/结论层（FR1）。

结论层双层结构（实现方案 §1）：note 写 SQLite 的同时导出 md 快照到 data/notes/，
保证仓库里永远有一份人可读、可 git diff 的结论。
"""
from fastapi import APIRouter, HTTPException

from ..config import NOTES_DIR
from ..db import conn
from ..schemas import FundIn, FundOut, FundPatch, NoteIn, NoteOut

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
