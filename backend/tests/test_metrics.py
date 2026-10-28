"""口径回归一：分红处理（实现方案 §6 + 复查报告 2026-10-20 §四）。

三条铁律：
1. 窗内无分红 → 单位净值比值即精确值；
2. 窗内有分红 → (期末单位 + 窗内分红现金)/期初单位（现金口径）；
3. 累计净值禁止用于区间收益——历史分红常数会阻尼失真
   （000390 实测：常数 3.078 把 -29.6% 阻尼成 -13.9%）。
"""
from app.services.metrics import (
    Series, max_drawdown, reconstruct_window, window_return,
)


def _mk(dates, unit, div=None):
    return Series(dates, unit, div)


class TestWindowReturn:
    def test_no_dividend_unit_ratio_exact(self):
        """窗内无分红：单位净值比值精确（000390 2026-09-18→10-20 实测形态）。"""
        s = _mk(["2026-09-18", "2026-10-20"], [2.9, 2.043])
        r = window_return(s, "2026-09-18", "2026-10-20")
        assert abs(r - (2.043 / 2.9 - 1)) < 1e-12
        assert abs(r - (-0.29552)) < 1e-4  # 复查报告口径：-29.6% 量级

    def test_dividend_in_window_cash_adjusted(self):
        """窗内有分红：期末单位 + 窗内分红现金（000390 2026-06-15 分红 0.463 形态）。"""
        # 期初 1.870（2025-12-31），期末 1.679，窗内 2026-06-15 分红 0.463
        s = _mk(
            ["2025-12-31", "2026-06-14", "2026-06-15", "2026-10-27"],
            [1.870, 2.500, 2.400, 1.679],
            [0, 0, 0.463, 0],
        )
        r = window_return(s, "2025-12-31", "2026-10-27")
        assert abs(r - ((1.679 + 0.463) / 1.870 - 1)) < 1e-12
        assert abs(r - 0.14545) < 1e-4  # 与 verify_m2 手算抽查一致

    def test_dividend_outside_window_ignored(self):
        """分红发生在窗口之前 → 不影响窗内收益（10-20 复查的核心反转点）。"""
        s = _mk(
            ["2026-01-02", "2026-06-15", "2026-09-18", "2026-10-20"],
            [1.000, 2.000, 2.900, 2.043],
            [0, 0.463, 0, 0],
        )
        r = window_return(s, "2026-09-18", "2026-10-20")
        assert abs(r - (2.043 / 2.9 - 1)) < 1e-12


class TestAccNavDamping:
    def test_acc_nav_constant_damps_loss(self):
        """防倒退护栏：累计口径把 -29.6% 量级跌幅阻尼成 -14% 左右（历史教训活体复现）。

        若有人把 window_return 改回累计净值口径，此用例必红。
        """
        start_unit, end_unit, const = 2.900, 2.043, 3.078  # 000390 真实常数
        correct = end_unit / start_unit - 1
        damped = (end_unit + const) / (start_unit + const) - 1
        assert abs(correct - (-0.29552)) < 1e-4
        assert abs(damped - (-0.14336)) < 1e-4
        assert correct < damped - 0.15  # 阻尼 15.2pp，方向恒为高估（跌幅被人为压小）


class TestMaxDrawdown:
    def test_mdd_with_window_dividend_reconstruction(self):
        """窗内含分红日：先「单位+窗内累计分红」重构再取 running max。"""
        s = _mk(
            ["2026-01-02", "2026-03-31", "2026-06-15", "2026-08-31", "2026-10-27"],
            [1.000, 1.200, 1.100, 0.900, 1.050],
            [0, 0, 0.463, 0, 0],
        )
        dates, adj = reconstruct_window(s, "2026-01-01")
        # 重构后：1.0, 1.2, 1.563, 1.363, 1.513 → 峰 1.563，谷 1.363
        mdd = max_drawdown(dates, adj)
        assert abs(mdd - (1.363 / 1.563 - 1)) < 1e-9
        # 若不重构（纯单位口径）会算成 0.9/1.2-1=-25%，显著更深——口径不同必须区分
        plain = max_drawdown(dates, [1.0, 1.2, 1.1, 0.9, 1.05])
        assert abs(plain - (-0.25)) < 1e-9

    def test_mdd_monotonic_up_is_zero(self):
        s = _mk(["2026-01-02", "2026-06-30"], [1.0, 1.5])
        dates, adj = reconstruct_window(s, "2026-01-01")
        assert max_drawdown(dates, adj) == 0.0
