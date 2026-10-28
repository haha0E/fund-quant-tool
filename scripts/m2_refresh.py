"""M2 摄取入口（可重跑）：名单入池 + 全量刷新 + 指标计算。

运行：uv run python scripts/m2_refresh.py [scope]
scope 缺省 all；重复运行走当日磁盘缓存，不重复外呼。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import init_db  # noqa: E402
from app.ingest import refresh as refresh_mod  # noqa: E402

if __name__ == "__main__":
    scope = sys.argv[1] if len(sys.argv) > 1 else "all"
    init_db()
    print(json.dumps(refresh_mod.seed_default_pool(), ensure_ascii=False))
    summary = refresh_mod.refresh(scope=scope)
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
