"""口径回归四：组合评估（M3，实现方案 §6 组合/基准对齐行的落点）。

铁律：
1. 等权每日再平衡：r_p = Σ w_i·r_i——单日收益直接可手算，合成净值从 1 累乘；
2. 相关性：完全同向 = 1，完全反向 = -1（构造序列而非真实数据，可复算）；
3. 完整性闸门成员（110005 先例）：差值负漂移 → 分红不采信、缺口显式、不阻断；
4. 默认权重 = my_position 份额×最新净值占比。
"""
from datetime import date, timedelta

import pytest

from app.db import get_conn, init_db
from app.services import portfolio as pf


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr("app.db.DB_PATH", db)
    init_db()
    yield db


def _days(n: int, start: str = "2026-01-01") -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def _seed_fund(db, code: str, unit: list[float], div: list[float] | None = None,
               acc_extra: list[float] | None = None):
    """acc = unit + extra（extra 单调不减即无负漂移；负漂移数据显式给）。"""
    div = div or [0.0] * len(unit)
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO fund (code, name, pool_type) VALUES (?, ?, 'research')",
                  (code, f"基金{code}"))
        for i, (d, u) in enumerate(zip(_days(len(unit)), unit)):
            acc = u + (acc_extra[i] if acc_extra else 0.0)
            c.execute(
                "INSERT OR REPLACE INTO fund_nav (code, date, unit_nav, acc_nav, dividend)"
                " VALUES (?, ?, ?, ?, ?)", (code, d, u, acc, div[i]))


class TestSynthesis:
    def test_equal_weight_daily_rebalance(self, tmp_db):
        """等权两只（A 日 +1%、B 日 -1%）→ 组合每日 0%，合成净值恒 1。"""
        n = 40
        a = [1.0 * (1.01 ** i) for i in range(n)]
        b = [2.0 * (0.99 ** i) for i in range(n)]
        _seed_fund(tmp_db, "A", a)
        _seed_fund(tmp_db, "B", b)
        r = pf.evaluate(["A", "B"], {"A": 0.5, "B": 0.5}, benchmark=None)
        assert all(abs(v - 1.0) < 1e-9 for v in r["portfolio_nav"])
        assert abs(r["portfolio_metric"]["ret_1m"] or 0) < 1e-9

    def test_common_dates_drop_qdii_lag(self, tmp_db):
        """QDII 滞后 1 天：非共同日整组剔除，共同窗内手算一致。"""
        days = _days(30)
        a = [1.0 * (1.01 ** i) for i in range(30)]
        _seed_fund(tmp_db, "A", a)
        with get_conn() as c:
            c.execute("INSERT OR IGNORE INTO fund (code, name, pool_type) VALUES ('Q', '基金Q', 'research')")
            for i, d in enumerate(days[:-1]):  # Q 少最后一天（T+1 滞后形态）
                c.execute("INSERT INTO fund_nav VALUES ('Q', ?, ?, ?, 0)",
                          (d, 1.0, 1.0))
        r = pf.evaluate(["A", "Q"], None, benchmark=None, weight_mode="equal")
        assert r["nav_dates"] == days[:-1]
        # 等权：日收益 = (1% + 0%) / 2
        assert abs(r["portfolio_nav"][-1] - (1.005 ** 28)) < 1e-9

    def test_integrity_member_div_ignored_with_gap(self, tmp_db):
        """差值负漂移成员（110005 先例）：分红置 0、缺口点名、仍出结果。"""
        n = 40
        unit = [1.0] * n
        unit[20] = 1.5  # 分红日（unit 跳升简化构造）
        div = [0.0] * n
        div[20] = 0.5
        # 差值序列 [0,...,0, 0.4, 0, ...,0]——负向漂移（1.5-0.5=1.0 vs 1.5+0-0=1.5?）
        # 构造：acc-extra 在分红日后回落 → has_negative_diff_drift=True
        extra = [0.0] * n
        extra[20] = 0.5      # acc = unit + 0.5（分红日）
        # 分红次日 unit 回到 1.0 而 extra 归 0 → 差值 0.5 → 0 负向
        _seed_fund(tmp_db, "G", unit, div, extra)
        r = pf.evaluate(["G"], None, benchmark=None, weight_mode="equal")
        assert any("G" in g and "漂移" in g for g in r["data_gaps"])
        assert len(r["portfolio_nav"]) > 0  # 不阻断


class TestCorrelation:
    def test_perfect_positive_and_negative(self, tmp_db):
        """同向 = 1、反向 = -1、零方差 = None（可复算构造：固定收益率方差为 0 不可用）。"""
        base = [0.02, -0.01, 0.015, -0.005, 0.01, -0.02, 0.025, 0.005, -0.012, 0.018] * 3

        def units(rets: list[float]) -> list[float]:
            out, v = [1.0], 1.0
            for r in rets:
                v *= 1 + r
                out.append(v)
            return out

        _seed_fund(tmp_db, "U", units(base))
        _seed_fund(tmp_db, "D", units([-r for r in base]))
        _seed_fund(tmp_db, "S", units([r + 0.001 for r in base]))  # 平移 → 完全正相关
        _seed_fund(tmp_db, "F", [1.0] * 31)  # 零方差 → corr=None（退化显式，不造 0）
        r = pf.evaluate(["U", "D", "S", "F"], None, benchmark=None, weight_mode="equal")
        m = {c: i for i, c in enumerate(r["corr_codes"])}
        assert r["corr_matrix"][m["U"]][m["D"]] == pytest.approx(-1.0, abs=1e-9)
        assert r["corr_matrix"][m["U"]][m["S"]] == pytest.approx(1.0, abs=1e-9)
        assert r["corr_matrix"][m["U"]][m["U"]] == 1.0
        assert r["corr_matrix"][m["U"]][m["F"]] is None


class TestBenchmarkExcess:
    def test_excess_on_common_window(self, tmp_db):
        """基准滞后形态：超额只按共同窗算（对齐铁律的组合版）。"""
        days = _days(40)
        up = [1.0 * (1.01 ** i) for i in range(40)]
        _seed_fund(tmp_db, "A", up)
        with get_conn() as c:
            for i, d in enumerate(days[:-2]):  # 基准数据早两天截止（滞后形态）
                c.execute("INSERT OR REPLACE INTO index_daily VALUES ('sh000300', ?, ?)",
                          (d, 100.0))  # 基准恒平
        r = pf.evaluate(["A"], None, benchmark="sh000300", weight_mode="equal")
        assert r["benchmark_nav"][-1] == pytest.approx(1.0)
        # 近1月窗口（30 天）在共同窗内：基金 1.01^29 vs 基准 0
        assert r["excess"]["ret_1m"] == pytest.approx(1.01 ** 30 - 1, rel=1e-6)
        assert r["excess"]["ret_1y"] == pytest.approx(1.01 ** 37 - 1, rel=1e-6)  # 不足1年窗回退全历史（对齐后 38 天）

    def test_benchmark_missing_not_fail(self, tmp_db):
        """基准未入库：缺口点名、组合结果照常。"""
        _seed_fund(tmp_db, "A", [1.0 * (1.01 ** i) for i in range(40)])
        r = pf.evaluate(["A"], None, benchmark="sh000852", weight_mode="equal")
        assert any("sh000852" in g for g in r["data_gaps"])
        assert len(r["portfolio_nav"]) == 40


class TestDefaultWeights:
    def test_position_weight_by_market_value(self, tmp_db):
        """默认权重 = 份额×最新净值占比（M3-1 落点）。"""
        _seed_fund(tmp_db, "A", [1.0, 2.0])   # 最新净值 2.0
        _seed_fund(tmp_db, "B", [1.0, 1.0])   # 最新净值 1.0
        with get_conn() as c:
            c.execute("INSERT INTO my_position VALUES ('A', 100, NULL, NULL, '2026-10-28')")
            c.execute("INSERT INTO my_position VALUES ('B', 100, NULL, NULL, '2026-10-28')")
        w = pf.default_weights_from_positions(["A", "B"])
        assert w == {"A": 2 / 3, "B": 1 / 3}

    def test_position_missing_returns_none(self, tmp_db):
        """任一成员未录份额 → None（调用方回退等权）。"""
        _seed_fund(tmp_db, "A", [1.0, 2.0])
        _seed_fund(tmp_db, "B", [1.0, 1.0])
        with get_conn() as c:
            c.execute("INSERT INTO my_position VALUES ('A', 100, NULL, NULL, '2026-10-28')")
        assert pf.default_weights_from_positions(["A", "B"]) is None
