"""口径回归二：基准对齐（实现方案 §6 基准对齐行）。

铁律：基金与基准先按共同交易日对齐再算超额——004195/012920 实测净值滞后
1 天，直接错位对比会虚增/虚减超额 2pp 量级。
"""
from app.services.metrics import align_common_dates, excess_return


def _fund_series():
    # QDII 形态：最新净值只到 10-26（T+1 滞后，10-27 尚未披露）
    return (["2026-10-24", "2026-10-25", "2026-10-26"],
            [1.000, 1.000, 1.000])


def _bench_series():
    # A 股指数：10-27 大跌 -2%（基金尚未经历该交易日）
    return (["2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"],
            [100.0, 100.0, 100.0, 98.0])


def test_align_keeps_common_dates_only():
    fd, fv = _fund_series()
    bd, bv = _bench_series()
    dates, a, b = align_common_dates(fd, fv, bd, bv)
    assert dates == ["2026-10-24", "2026-10-25", "2026-10-26"]
    assert a == [1.000, 1.000, 1.000]
    assert b == [100.0, 100.0, 100.0]


def test_misaligned_excess_inflates_by_2pp_class():
    """错位对比 vs 对齐后：超额被虚增 2pp（012920 滞后 1 天实测教训量级）。"""
    fd, fv = _fund_series()
    bd, bv = _bench_series()
    # 错位：基金窗 10-24→10-26 vs 指数窗 10-24→10-27（各自最新可得首尾）
    wrong_fund = fv[-1] / fv[0] - 1          # 0%
    wrong_bench = bv[-1] / bv[0] - 1         # -2%（含基金未经历的 10-27）
    wrong_excess = excess_return(wrong_fund, wrong_bench)  # +2% 虚增

    _, a, b = align_common_dates(fd, fv, bd, bv)
    right_fund = a[-1] / a[0] - 1            # 0%
    right_bench = b[-1] / b[0] - 1           # 0%（截止共同日 10-26）
    right_excess = excess_return(right_fund, right_bench)  # 0%

    assert abs(wrong_excess - right_excess) >= 0.02  # 实测教训量级：2pp
    assert wrong_excess > right_excess                # 方向：虚增（反向场景则虚减）


def test_align_empty_intersection():
    dates, a, b = align_common_dates(["2026-01-01"], [1.0], ["2026-02-01"], [2.0])
    assert (dates, a, b) == ([], [], [])
