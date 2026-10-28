"""M4 验收自检（§5 原文：新易盛/中际旭创组合权重排前列、超标标色；报告期滞后标注）。

跑法：uv run python scripts/verify_m4.py（在 backend/ 目录下 uv run 亦可）。
用真实库 + 真实持仓数据断言，不复算——只验证交付事实。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import init_db  # noqa: E402
from app.services.overlap import OVER_LIMIT, overlap  # noqa: E402

PASS, FAIL = "\x1b[32m[PASS]\x1b[0m", "\x1b[31m[FAIL]\x1b[0m"
ok = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    ok = ok and cond
    print(f"{PASS if cond else FAIL} {name}" + (f" | {detail}" if detail else ""))


def main() -> None:
    init_db()
    # 持仓 4 只等权（验收场景：2026-10-13 诊断的复现口径）
    codes = ["000390", "004195", "012920", "022364"]
    r = overlap(codes, {c: 0.25 for c in codes})

    print(f"== M4 穿透验收（持仓 {len(r['members'])} 只等权，报告期 "
          f"{r['members'][0]['report_date']}，滞后 {r['max_lag_days']} 天）==")

    top5 = [(s["stock_name"], round(s["weight"] * 100, 2)) for s in r["stocks"][:5]]
    names_top5 = [n for n, _ in top5]
    check("新易盛排前 5", "新易盛" in names_top5, f"前5：{top5}")
    check("中际旭创排前 5", "中际旭创" in names_top5, "")
    check("两者均被 ≥2 只基金共同持有（重叠事实）",
          all(s["fund_count"] >= 2 for s in r["stocks"][:2]
              if s["stock_name"] in ("新易盛", "中际旭创")),
          str([(s["stock_name"], s["fund_count"]) for s in r["stocks"][:2]]))
    check(f"超标标色阈值就位（单股 >{OVER_LIMIT:.0%} 红，前端按此渲染）",
          OVER_LIMIT == 0.10)
    check("报告期滞后已标注（PRD 显眼标注要求）",
          r["max_lag_days"] > 0 and all(m["report_date"] for m in r["members"]),
          f"最大滞后 {r['max_lag_days']} 天")
    check("未披露部分条目存在（防穿透精度高估）",
          0 < r["undisclosed"] < 1, f"未披露 {r['undisclosed']:.1%}")
    check("有效持仓数已计（≥1% 阈值）", r["effective_count"] > 0,
          f"{r['effective_count']} 只")

    print("\nM4 自检" + ("全部通过 ✓" if ok else "存在未通过项 ✗"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
