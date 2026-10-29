"""领域探索接口（M5，实现方案 §4：GET /api/explore/domains + /{domain} + POST /pool）。

数据降级序（实现方案 §2.2）：domain_map 快照（ZCode 周更映射）优先 →
miss 时全市场排行按名称关键词粗筛（复用 preflight 的 _TAG_RULES 词表）。
排行收益是数据商区间涨幅（%），只用于候选粗筛排序；入池后指标一律库内 §6 自算。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import conn
from ..ingest import source_map
from ..routers.funds import _suggest_tags
from ..schemas import FundOut

router = APIRouter(prefix="/api/explore", tags=["explore"])

# 探索页可发现的领域全集：关键词规则领域 + 池内已用标签
_RULE_DOMAINS = ["医药", "机器人", "AI算力", "黄金", "红利", "消费", "宽基", "QDII"]
_MAX_CANDIDATES = 60


@router.get("/domains")
def list_domains():
    """领域列表：快照映射计数 + 池内标签计数（两路合并，界面选择器）。"""
    with conn() as c:
        snap = dict(c.execute(
            "SELECT domain, COUNT(*) FROM domain_map GROUP BY domain").fetchall())
        pool = {}
        for row in c.execute("SELECT domain_tags FROM fund"):
            for t in (row["domain_tags"] or "").split(","):
                if t.strip():
                    pool[t.strip()] = pool.get(t.strip(), 0) + 1
    domains = []
    for d in dict.fromkeys([*_RULE_DOMAINS, *sorted(snap), *sorted(pool)]):
        domains.append({"domain": d, "snapshot_funds": snap.get(d, 0),
                        "pool_funds": pool.get(d, 0)})
    return domains


@router.get("/{domain}")
def explore_domain(domain: str):
    """领域内候选：快照映射优先（源=快照），miss 走排行关键词粗筛（源=排行粗筛）。

    返回含池内外标注；排行口径仅粗筛排序用，界面明示。"""
    with conn() as c:
        pool_rows = c.execute("SELECT code, name, domain_tags FROM fund").fetchall()
        snap_rows = c.execute(
            "SELECT fund_code, fund_name FROM domain_map WHERE domain = ?"
            " ORDER BY updated_at DESC", (domain,)).fetchall()

    out: dict[str, dict] = {}

    def _put(code: str, name: str, source: str, ret: dict | None = None) -> None:
        out[code] = {"code": code, "name": name or code,
                     "source": source, "in_pool": any(r["code"] == code for r in pool_rows),
                     "ret_1m": ret and ret.get("ret_1m"),
                     "ret_3m": ret and ret.get("ret_3m"),
                     "ret_6m": ret and ret.get("ret_6m"),
                     "ret_1y": ret and ret.get("ret_1y"),
                     "ret_ytd": ret and ret.get("ret_ytd")}

    # 优先级：快照映射（ZCode 周更）> 池内标签直配 > 排行关键词粗筛
    for r in snap_rows:
        _put(r["fund_code"], r["fund_name"] or "", "快照映射")
    for r in pool_rows:
        tags = [t.strip() for t in (r["domain_tags"] or "").split(",") if t.strip()]
        if domain in tags and r["code"] not in out:
            _put(r["code"], r["name"] or "", "池内标签")
    if len(out) < _MAX_CANDIDATES:
        try:
            rank = source_map.fetch("fund_rank")
        except Exception as e:  # noqa: BLE001 排行拉不到不 500：快照/池内命中的照常返回
            if not out:
                raise HTTPException(502, f"排行数据拉取失败且无快照映射：{e}") from e
            return {"domain": domain, "candidates": list(out.values())[:_MAX_CANDIDATES],
                    "warning": f"排行粗筛不可用（{str(e)[:80]}），仅快照映射/池内"}
        words = _domain_keywords(domain)
        matched = [r for r in rank
                   if any(w in r["name"] for w in words) and r["code"] not in out]
        matched.sort(key=lambda r: (r.get("ret_1y") is None, -(r.get("ret_1y") or 0)))
        for r in matched[: _MAX_CANDIDATES - len(out)]:
            _put(r["code"], r["name"], "排行粗筛", r)
        # 池内/快照来源的也用排行数据补收益（展示统一口径）
        by_code = {r["code"]: r for r in rank}
        for code, entry in out.items():
            if entry["ret_1y"] is None and code in by_code:
                r = by_code[code]
                entry.update({"ret_1m": r.get("ret_1m"), "ret_3m": r.get("ret_3m"),
                              "ret_6m": r.get("ret_6m"), "ret_1y": r.get("ret_1y"),
                              "ret_ytd": r.get("ret_ytd")})
    return {"domain": domain, "candidates": list(out.values())[:_MAX_CANDIDATES]}


def _domain_keywords(domain: str) -> list[str]:
    """领域 → 排行名称粗筛词表（与 preflight._suggest_tags 同源，保持一致性）。"""
    table = {
        "医药": ("医药", "创新药", "医疗", "生物", "健康"),
        "机器人": ("机器人",),
        "AI算力": ("算力", "人工智能", "半导体", "芯片", "集成电路", "计算机", "光模块"),
        "黄金": ("黄金", "贵金属"),
        "红利": ("红利", "股息"),
        "消费": ("消费", "白酒", "食品饮料"),
        "宽基": ("沪深300", "中证500", "中证800", "中证1000", "中证A500", "上证50",
                 "创业板", "科创50", "中证全指"),
        "QDII": ("QDII", "全球精选", "海外", "美国", "纳斯达克", "恒生"),
    }
    return list(table.get(domain, (domain,)))


class ExplorePoolIn(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    domain_tags: list[str] = Field(default_factory=list, max_length=5)


@router.post("/pool", response_model=FundOut, status_code=201)
def add_to_research_pool(body: ExplorePoolIn):
    """领域探索页入研究池：名字由排行/快照回填（不再外呼），标签默认=领域。"""
    from .funds import _tags_to_str
    name = ""
    try:
        for r in source_map.fetch("fund_rank"):
            if r["code"] == body.code:
                name = r["name"]
                break
    except Exception:  # noqa: BLE001 排行不可用时名字留空（详情页刷新会回填）
        pass
    if not name:
        with conn() as c:
            row = c.execute("SELECT fund_name FROM domain_map WHERE fund_code = ?",
                            (body.code,)).fetchone()
            name = row["fund_name"] if row and row["fund_name"] else ""
    with conn() as c:
        if c.execute("SELECT 1 FROM fund WHERE code = ?", (body.code,)).fetchone():
            raise HTTPException(409, f"基金 {body.code} 已在池中")
        c.execute(
            "INSERT INTO fund (code, name, pool_type, domain_tags) VALUES (?, ?, 'research', ?)",
            (body.code, name, _tags_to_str(body.domain_tags or [])))
        row = c.execute(
            """SELECT f.code, f.name, f.pool_type, f.domain_tags, f.created_at,
                      EXISTS(SELECT 1 FROM note n WHERE n.fund_code = f.code) AS has_note
               FROM fund f WHERE f.code = ?""", (body.code,)).fetchone()
    return FundOut(code=row["code"], name=row["name"], pool_type=row["pool_type"],
                   domain_tags=[t for t in row["domain_tags"].split(",") if t],
                   created_at=row["created_at"], has_note=bool(row["has_note"]))
