"""M5 验收自检（§5 原文：医药领域入池 000960 跑通；快照幂等导入）。

跑法：cd backend && uv run python ../scripts/verify_m5.py
医药入池验收说明：000960 已在 M2 播种进研究池（PRD 验收①语境），本脚本验证
① 医药领域列表含 000960 且正确标注已在池；② 入池链路（explore/pool + 标签）
用测试标的完整走通后清理；③ 快照幂等（临时目录导入两次行数不变）。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import SNAPSHOT_DIR  # noqa: E402
from app.db import conn, init_db  # noqa: E402
from app.ingest.snapshot_import import import_snapshots  # noqa: E402
from app.routers import explore  # noqa: E402

PASS, FAIL = "\x1b[32m[PASS]\x1b[0m", "\x1b[31m[FAIL]\x1b[0m"
ok = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    ok = ok and cond
    print(f"{PASS if cond else FAIL} {name}" + (f" | {detail}" if detail else ""))


def main() -> None:
    init_db()

    # ① 医药领域列表
    result = explore.explore_domain("医药")
    cands = result["candidates"]
    med = [c for c in cands if c["code"] == "000960"]
    check("医药领域候选非空", len(cands) > 10, f"{len(cands)} 只候选")
    check("000960 出现在医药领域列表", len(med) == 1)
    check("000960 标注已在池（研究池成员）", med and med[0]["in_pool"] is True,
          med[0]["name"] if med else "")

    # ② 入池链路（测试标的 161725 入池→验证→清理，不动真实池）
    test_code = "161725"
    with conn() as c:
        c.execute("DELETE FROM fund WHERE code = ?", (test_code,))
    try:
        fund = explore.add_to_research_pool(
            explore.ExplorePoolIn(code=test_code, domain_tags=["消费"]))
        check("explore/pool 入池成功（名字回填）", bool(fund.name) and fund.pool_type == "research",
              f"{fund.code} {fund.name}")
        check("入池标签自动打上", "消费" in fund.domain_tags)
    finally:
        with conn() as c:
            c.execute("DELETE FROM fund WHERE code = ?", (test_code,))
    print("[INFO] 测试标的已清理")

    # ③ 快照幂等（临时快照目录，验收后清理）
    test_dir = SNAPSHOT_DIR / "2026-01-01"
    backup = None
    if test_dir.exists():
        backup = SNAPSHOT_DIR / "2026-01-01.bak"
        shutil.move(str(test_dir), str(backup))
    try:
        test_dir.mkdir(parents=True)
        (test_dir / "domain_map.csv").write_text(
            "\ufeffdomain,fund_code,fund_name\n医药,000960,招商医药健康产业股票\n", encoding="utf-8")
        with conn() as c:
            c.execute("DELETE FROM snapshot_log WHERE snapshot_date='2026-01-01'")
            c.execute("DELETE FROM domain_map WHERE fund_code='000960' AND domain='医药'")
        r1 = import_snapshots()
        with conn() as c:
            n1 = c.execute("SELECT COUNT(*) FROM domain_map WHERE fund_code='000960'").fetchone()[0]
        r2 = import_snapshots()
        with conn() as c:
            n2 = c.execute("SELECT COUNT(*) FROM domain_map WHERE fund_code='000960'").fetchone()[0]
        check("快照导入记账", len(r1["imported"]) == 1 and r1["imported"][0]["rows"] == 1)
        check("幂等：二次导入跳过且行数不变",
              len(r2["imported"]) == 0 and len(r2["skipped"]) >= 1 and n1 == n2,
              f"第一次 {n1} 行 / 第二次 {n2} 行")
    finally:
        with conn() as c:
            c.execute("DELETE FROM snapshot_log WHERE snapshot_date='2026-01-01'")
            c.execute("DELETE FROM domain_map WHERE fund_code='000960'")
        shutil.rmtree(test_dir, ignore_errors=True)
        if backup and backup.exists():
            shutil.move(str(backup), str(test_dir))
    print("[INFO] 快照测试数据已清理")

    print("\nM5 自检" + ("全部通过 ✓" if ok else "存在未通过项 ✗"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
