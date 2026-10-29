"""口径回归六：快照幂等导入 + 领域探索（M5，实现方案 §2.2/§4）。

铁律：
1. 快照幂等：同目录导入两次，domain_map 行数不变（记账跳过 + 唯一键 UPSERT 双保险）；
2. 非日期目录/不认识的文件名跳过不报错；
3. 快照映射优先于池内标签与排行粗筛（降级序）。
"""
from pathlib import Path

import pytest

from app.db import conn, get_conn, init_db
from app.ingest.snapshot_import import import_snapshots


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    snap_root = tmp_path / "snapshot"
    monkeypatch.setattr("app.db.DB_PATH", db)
    monkeypatch.setattr("app.config.SNAPSHOT_DIR", snap_root)
    import app.ingest.snapshot_import as si
    monkeypatch.setattr(si, "SNAPSHOT_DIR", snap_root)
    init_db()
    return snap_root


def _write_snapshot(root: Path, day: str, content: str) -> None:
    d = root / day
    d.mkdir(parents=True, exist_ok=True)
    (d / "domain_map.csv").write_text("\ufeff" + content, encoding="utf-8")


class TestSnapshotImport:
    def test_idempotent_double_import(self, tmp_env):
        """M5 验收线：导入两次行数不变。"""
        _write_snapshot(tmp_env, "2026-10-20",
                        "domain,fund_code,fund_name\n医药,000960,招商医药\nAI算力,022364,永赢\n")
        r1 = import_snapshots()
        assert len(r1["imported"]) == 1 and r1["imported"][0]["rows"] == 2
        with conn() as c:
            assert c.execute("SELECT COUNT(*) FROM domain_map").fetchone()[0] == 2
        r2 = import_snapshots()
        assert r2["imported"] == [] and len(r2["skipped"]) == 1
        with conn() as c:
            assert c.execute("SELECT COUNT(*) FROM domain_map").fetchone()[0] == 2

    def test_reimport_after_content_change_upserts(self, tmp_env):
        """同日期重复导入被跳过；但手工清记账后重导走 UPSERT 更新而非重复行。"""
        _write_snapshot(tmp_env, "2026-10-21", "domain,fund_code,fund_name\n医药,000960,旧名\n")
        import_snapshots()
        _write_snapshot(tmp_env, "2026-10-21", "domain,fund_code,fund_name\n医药,000960,新名\n")
        with conn() as c:  # 模拟重新处理：清记账
            c.execute("DELETE FROM snapshot_log")
        import_snapshots()
        with conn() as c:
            n = c.execute("SELECT COUNT(*) FROM domain_map WHERE fund_code='000960'").fetchone()[0]
            name = c.execute("SELECT fund_name FROM domain_map WHERE fund_code='000960'").fetchone()[0]
        assert n == 1 and name == "新名"

    def test_skips_non_date_dirs_and_unknown_files(self, tmp_env):
        (tmp_env / "not-a-date").mkdir(parents=True)
        (tmp_env / "not-a-date" / "domain_map.csv").write_text("x,y,z", encoding="utf-8")
        (tmp_env / "2026-10-22").mkdir()
        (tmp_env / "2026-10-22" / "random.txt").write_text("junk", encoding="utf-8")
        r = import_snapshots()
        assert r["imported"] == [] and r["errors"] == []

    def test_empty_or_dirty_rows_ignored(self, tmp_env):
        _write_snapshot(tmp_env, "2026-10-23",
                        "domain,fund_code,fund_name\n,000960,x\n医药,,y\n医药,000961,z\n")
        r = import_snapshots()
        assert r["imported"][0]["rows"] == 1  # 空域/空代码行剔除，不造假


class TestExploreFallback:
    def test_snapshot_priority_over_pool_tags(self, tmp_env):
        """快照映射与池内标签同现时，快照来源优先（同一 code 不重复出两条）。"""
        with get_conn() as c:
            c.execute("INSERT INTO fund (code, name, pool_type, domain_tags)"
                      " VALUES ('000960', '招商医药', 'research', '医药')")
        _write_snapshot(tmp_env, "2026-10-24", "domain,fund_code,fund_name\n医药,000960,快照名\n")
        import_snapshots()
        from app.routers import explore
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(explore.source_map, "fetch",
                       lambda kind, **kw: (_ for _ in ()).throw(RuntimeError("排行不可用")))
            result = explore.explore_domain("医药")
        cands = result["candidates"]
        assert len(cands) == 1
        assert cands[0]["source"] == "快照映射" and cands[0]["in_pool"] is True
        assert "warning" in result  # 排行失败但快照兜住，明示而非静默
