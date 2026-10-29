"""快照导入接口（M5）：POST /api/snapshot/import（幂等）+ GET /api/snapshot/status。

任务计划每日调 import（§7）；手动也可随时调，重复导入不产生重复行。
"""
from fastapi import APIRouter

from ..db import conn
from ..ingest.snapshot_import import import_snapshots

router = APIRouter(prefix="/api/snapshot", tags=["snapshot"])


@router.post("/import")
def import_snapshot():
    return import_snapshots()


@router.get("/status")
def snapshot_status():
    with conn() as c:
        rows = c.execute(
            "SELECT snapshot_date, filename, rows, imported_at FROM snapshot_log"
            " ORDER BY snapshot_date DESC, filename").fetchall()
    return {"imported": [dict(r) for r in rows],
            "total_files": len(rows)}
