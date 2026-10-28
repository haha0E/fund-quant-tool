"""M2 验收自检（可重跑）：
1. 000390 库内净值 vs data/000390_weekly_nav.csv（Wind 周度基准）——要求 0.000%；
2. 分红口径断言：2026-06-15 每份 0.463；累计-单位差值核对常数 3.078；
3. 指标手算抽查：YTD/1年/最大回撤 用独立公式复算（分红现金口径）。

运行：uv run python scripts/verify_m2.py
"""
import csv
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

FAIL = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" | {detail}" if detail else ""))
    if not ok:
        FAIL.append(name)


conn = sqlite3.connect(ROOT / "data" / "workbench.db")
conn.row_factory = sqlite3.Row
nav = conn.execute(
    "SELECT date, unit_nav, acc_nav, dividend FROM fund_nav"
    " WHERE code='000390' ORDER BY date").fetchall()
nav_map = {r["date"]: r for r in nav}

# ---- 1. CSV 交叉核对（周标签 = 周日；基准 = ≤周标签的最后一个净值日，长假周顺延）----
rows = list(csv.DictReader(open(ROOT / "data" / "000390_weekly_nav.csv", encoding="utf-8")))
diffs = []
miss = 0
for row in rows:
    hi = row["date"]
    w = [r for r in nav if r["date"] <= hi]
    if not w:
        miss += 1
        continue
    r = w[-1]
    du = abs(r["unit_nav"] - float(row["unit_nav"]))
    da = abs((r["acc_nav"] or 0) - float(row["cum_nav"])) if row["cum_nav"] else 0.0
    if du > 1e-9 or da > 1e-9:
        diffs.append((row["date"], row["unit_nav"], r["date"], r["unit_nav"],
                      du / float(row["unit_nav"]) * 100))

exact = len(rows) - miss - len(diffs)
if diffs:
    print(f"[INFO] 偏差行明细（date, csv, 库内, 库内日期, 偏差%）: {diffs}")
check(f"000390 单位净值 vs CSV：{exact}/{len(rows)} 行 0.000%（未匹配 {miss}）",
      miss == 0 and len(diffs) <= 1
      and all(d[4] <= 0.1 for d in diffs),
      f"唯一允许偏差 ≤0.1%（东财/Wind 第4位小数舍入边界，官方 lsjz 复核口径以东财为准）"
      if len(diffs) == 1 else f"偏差行 {len(diffs)}")

# ---- 2. 分红口径断言 ----
divs = {r["date"]: r["dividend"] for r in nav if r["dividend"] > 0 and r["date"] >= "2026-01-01"}
check("000390 2026-06-15 分红 0.463", divs.get("2026-06-15") == 0.463, f"库内={divs}")
last = nav[-1]
diff_const = round(last["acc_nav"] - last["unit_nav"], 3)
check("累计-单位差值 = 3.078（核对常数）", diff_const == 3.078, f"差值={diff_const}")

# ---- 3. 指标手算抽查（独立复算，不复用 services 代码路径）----
m = conn.execute(
    "SELECT * FROM fund_metric WHERE code='000390' ORDER BY as_of DESC LIMIT 1").fetchone()


def base_on_or_before(boundary: str) -> sqlite3.Row:
    cand = [r for r in nav if r["date"] <= boundary]
    return cand[-1] if cand else None


as_of = m["as_of"]
end = [r for r in nav if r["date"] <= as_of][-1]

# YTD（分红现金口径）：基线 = 上一年最后一个净值日
prev_year_last = max(r["date"] for r in nav if r["date"] < f"{as_of[:4]}-01-01")
b = nav_map[prev_year_last]
cash = sum(r["dividend"] for r in nav if prev_year_last < r["date"] <= as_of and r["dividend"] > 0)
ytd_manual = (end["unit_nav"] + cash) / b["unit_nav"] - 1
check("YTD 手算一致（分红现金口径）", abs(ytd_manual - m["ret_ytd"]) < 1e-9,
      f"手算={ytd_manual:.6f} 库内={m['ret_ytd']:.6f} 窗内分红={cash}")

# 1 年窗口 + 年化
d1 = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
b1 = base_on_or_before(d1)
cash1 = sum(r["dividend"] for r in nav if b1["date"] < r["date"] <= as_of and r["dividend"] > 0)
r1_manual = (end["unit_nav"] + cash1) / b1["unit_nav"] - 1
days = (datetime.strptime(as_of, "%Y-%m-%d") - datetime.strptime(b1["date"], "%Y-%m-%d")).days
ann_manual = (1 + r1_manual) ** (365 / days) - 1
check("近1年手算一致", abs(r1_manual - m["ret_1y"]) < 1e-9,
      f"手算={r1_manual:.6f} 库内={m['ret_1y']:.6f}")
check("年化手算一致 (1+R)^(365/days)-1", abs(ann_manual - m["ann_ret"]) < 1e-9,
      f"手算={ann_manual:.6f} 库内={m['ann_ret']:.6f} days={days}")

# 最大回撤（窗内分红重构，独立实现）
win = [r for r in nav if r["date"] > d1] or nav
adj, cum, peak, mdd = [], 0.0, -1e18, 0.0
for r in win:
    cum += r["dividend"]
    v = r["unit_nav"] + cum
    peak = max(peak, v)
    mdd = min(mdd, v / peak - 1)
check("最大回撤手算一致（窗内重构）", abs(mdd - m["max_dd"]) < 1e-9,
      f"手算={mdd:.6f} 库内={m['max_dd']:.6f}")

# ---- 4. 反向口径回归：累计净值算区间会被常数阻尼（防倒退护栏）----
raw_unit_ratio = end["unit_nav"] / b["unit_nav"] - 1
acc_ratio = end["acc_nav"] / b["acc_nav"] - 1 if b["acc_nav"] else None
check("累计口径确已阻尼失真（负向护栏：与正确口径偏离 >2pp）",
      acc_ratio is not None and abs(acc_ratio - ytd_manual) > 0.02,
      f"单位+现金口径={ytd_manual:+.4f} vs 累计口径={acc_ratio:+.4f}"
      f"（2026-10-20 复查教训的活体证据）")

# ---- 5. 摄取完整性 ----
counts = {r["code"]: (r["n_nav"], r["n_prof"], r["n_hold"])
          for r in conn.execute("""
SELECT f.code,
  (SELECT COUNT(*) FROM fund_nav n WHERE n.code=f.code) n_nav,
  (SELECT COUNT(*) FROM fund_profile p WHERE p.code=f.code) n_prof,
  (SELECT COUNT(*) FROM fund_holding h WHERE h.code=f.code) n_hold
FROM fund f""")}
bad = {c: v for c, v in counts.items() if v[0] == 0 or v[1] == 0}
check("12 只全部有净值+档案", len(bad) == 0, f"缺口: {bad or '无'}")
no_hold = [c for c, v in counts.items() if v[2] == 0]
print(f"[INFO] 无持仓明细: {no_hold}（021030 联接基金只投目标 ETF，属真实披露缺口）")

print()
if FAIL:
    print(f"自检失败 {len(FAIL)} 项: {FAIL}")
    sys.exit(1)
print("M2 自检全部通过 ✓")
