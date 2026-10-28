"""手动刷新接口（实现方案 §4）：POST /api/refresh?scope=nav|profile|holdings|metrics|all。

任务计划程序（M5）也调它。同步执行——12 只全量首刷约 1-2 分钟（反爬 sleep
是主要耗时），前端 loading 提示；当日磁盘缓存保证重复调用不再外呼。
"""
from fastapi import APIRouter, HTTPException, Query

from ..ingest import refresh as refresh_mod

router = APIRouter(prefix="/api/refresh", tags=["refresh"])

_SCOPES = ("nav", "profile", "holdings", "metrics", "all")


@router.post("")
def trigger_refresh(scope: str = Query("all"), code: str | None = Query(None),
                     seed: bool = Query(False)):
    """code 传入时只刷该基金（画像页单刷），缺省刷全池。"""
    if scope not in _SCOPES:
        raise HTTPException(400, f"scope 须为 {'/'.join(_SCOPES)}")
    seeded = refresh_mod.seed_default_pool() if seed else None
    summary = refresh_mod.refresh(scope=scope, codes=[code] if code else None)
    return {"scope": scope, "code": code, "seeded": seeded, **summary}
