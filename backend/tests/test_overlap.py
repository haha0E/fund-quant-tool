"""口径回归五：穿透分析（M4，PRD FR2③/FR3 + 实现方案 §6 穿透权重行）。

铁律：
1. 穿透权重 = Σ(基金权重 × 个股占净值比/100)，同名股（代码相同）合并；
2. 未披露部分 = 1 − Σ(基金权重 × 前十大合计占比)，防穿透精度被高估；
3. 有效持仓数按阈值（≥1%）计数；
4. 港股/美股代码（非 6 位 A 股）标 a_share=False 不算指标；
5. 报告期滞后按成员最新 report_date 计天数。
"""
from datetime import date, timedelta

import pytest

from app.db import get_conn, init_db
from app.services import overlap as ol


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("app.db.DB_PATH", db)
    init_db()
    yield db


def _seed_holdings(db, code: str, report_date: str, rows: list[tuple[str, str, float]]):
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO fund (code, name, pool_type) VALUES (?, ?, 'holding')",
                  (code, f"基金{code}"))
        for stock_code, stock_name, weight in rows:
            c.execute(
                "INSERT OR REPLACE INTO fund_holding (code, report_date, stock_code, stock_name, weight)"
                " VALUES (?, ?, ?, ?, ?)", (code, report_date, stock_code, stock_name, weight))


class TestPenetration:
    def test_same_stock_merged_across_funds(self, tmp_db):
        """同名股合并：A(权重0.5, 持仓8%) + B(权重0.5, 持仓4%) → 穿透 6%。"""
        today = date.today().isoformat()
        _seed_holdings(tmp_db, "A", today, [("300502", "新易盛", 8.0), ("600000", "浦发", 2.0)])
        _seed_holdings(tmp_db, "B", today, [("300502", "新易盛", 4.0), ("000001", "平安", 6.0)])
        r = ol.overlap(["A", "B"], {"A": 0.5, "B": 0.5})
        by = {s["stock_code"]: s for s in r["stocks"]}
        assert by["300502"]["weight"] == pytest.approx(0.5 * 0.08 + 0.5 * 0.04)
        assert by["300502"]["fund_count"] == 2
        # 排序：新易盛 6% 第一
        assert r["stocks"][0]["stock_code"] == "300502"

    def test_undisclosed_and_effective_count(self, tmp_db):
        """未披露 = 1 − Σ(基金权重×前十大合计)；有效持仓数按 ≥1%。"""
        today = date.today().isoformat()
        rows = [(f"60000{i}", f"股{i}", 5.0) for i in range(10)]  # 前十大各 5% → 合计 50%
        _seed_holdings(tmp_db, "A", today, rows)
        r = ol.overlap(["A"], {"A": 1.0})
        assert r["undisclosed"] == pytest.approx(1 - 0.50)
        assert r["effective_count"] == 10  # 每只穿透 5% ≥1%
        assert all(s["weight"] == pytest.approx(0.05) for s in r["stocks"])

    def test_manual_weights_reflect_in_penetration(self, tmp_db):
        """手调权重（0.8/0.2）如实进穿透：0.8×10% + 0.2×5% = 9%。"""
        today = date.today().isoformat()
        _seed_holdings(tmp_db, "A", today, [("300502", "新易盛", 10.0)])
        _seed_holdings(tmp_db, "B", today, [("300502", "新易盛", 5.0)])
        r = ol.overlap(["A", "B"], {"A": 0.8, "B": 0.2})
        assert r["stocks"][0]["weight"] == pytest.approx(0.8 * 0.10 + 0.2 * 0.05)

    def test_over_limit_flag_threshold(self, tmp_db):
        """PRD 标色阈值常量：单股 >10% 红。"""
        assert ol.OVER_LIMIT == 0.10
        assert ol.EFFECTIVE_MIN_WEIGHT == 0.01


class TestHonesty:
    def test_lag_days_per_member(self, tmp_db):
        """报告期滞后：90 天前的报告期 → lag_days≈90。"""
        old = (date.today() - timedelta(days=90)).isoformat()
        _seed_holdings(tmp_db, "A", old, [("300502", "新易盛", 10.0)])
        r = ol.overlap(["A"], {"A": 1.0})
        assert r["members"][0]["lag_days"] == 90
        assert r["max_lag_days"] == 90

    def test_non_a_share_flagged_not_crash(self, tmp_db):
        """美股 ticker（QDII 持仓）标 a_share=False、指标空、不进刷新清单。"""
        today = date.today().isoformat()
        _seed_holdings(tmp_db, "A", today, [("NVDA", "英伟达", 9.0), ("300502", "新易盛", 8.0)])
        r = ol.overlap(["A"], {"A": 1.0})
        by = {s["stock_code"]: s for s in r["stocks"]}
        assert by["NVDA"]["a_share"] is False
        assert by["NVDA"]["pe_ttm"] is None
        assert by["300502"]["a_share"] is True
        assert any("美股" in g or "港股" in g for g in r["data_gaps"])

    def test_missing_holdings_reported_not_fake(self, tmp_db):
        """无持仓披露的成员：点名缺口，不产出假数据。"""
        with get_conn() as c:
            c.execute("INSERT INTO fund (code, name, pool_type) VALUES ('X', '基金X', 'holding')")
        r = ol.overlap(["X"], {"X": 1.0})
        assert r["members"] == []
        assert any("X" in g for g in r["data_gaps"])


class TestPercentile:
    def test_percentile_of_latest(self):
        from app.services.metrics import percentile_of_latest
        assert percentile_of_latest([1, 2, 3, 4, 5]) == pytest.approx(1.0)   # 末位最大
        assert percentile_of_latest([5, 4, 3, 2, 1]) == pytest.approx(0.2)   # 末位最小占 1/5
        assert percentile_of_latest([None, None]) is None
        assert percentile_of_latest([]) is None
