"""第三次调查脚本（2026-10-20）：持仓 5 只 + 候选 6 只。
对比基线：09-18（第4期周报业绩截止，回调起点）、10-16（上次核查数据点）。
升级：① 区间收益 = 单位净值 + 窗内分红现金修正（**禁止累计净值算区间**——历史分红常数
   会阻尼失真：000390 的累计-单位差 3.078 会把真实 -29.6% 阻尼成 -13.9%，10-20 实测教训）
   ② 新增光模块个股 20 日线信号 ③ 新浪源基准。
只读不写。运行：uv run python -X utf8 scripts/recheck_advice_20261020.py
"""
import akshare as ak
import pandas as pd

pd.set_option("display.width", 220)

FUNDS = {
    "022364": "永赢科技智选A",
    "000390": "华商优势行业A",
    "011369": "华商均衡成长A",
    "004195": "招商中证1000增强C",
    "012920": "易方达全球成长精选A",
    "001411": "诺安创新驱动A(存储·观察)",
    "110005": "易方达积极成长(设备·观察)",
    "021030": "汇添富港股通创新药联接A(定投候选)",
    "006113": "汇添富创新医药A(定投候选)",
    "020972": "易方达机器人联接A(观察)",
    "018344": "华夏机器人联接A(观察)",
}
BASE_0918 = "2026-09-18"   # 回调起点
BASE_1016 = "2026-10-16"   # 上次核查数据点
YEAR_START = "2026-01-01"
END = "2026-10-20"


def nav_tables(code: str):
    """返回 (单位净值表, 累计净值表)，列统一为 date/nav"""
    out = []
    for ind, kw in (("单位净值走势", "单位净值"), ("累计净值走势", "累计净值")):
        df = ak.fund_open_fund_info_em(symbol=code, indicator=ind)
        df = df.rename(columns=lambda c: c.strip())
        d, v = [c for c in df.columns if "日期" in c][0], [c for c in df.columns if kw in c][0]
        df[d] = pd.to_datetime(df[d])
        df[v] = pd.to_numeric(df[v], errors="coerce")
        out.append(df.dropna(subset=[v]).reset_index(drop=True).rename(columns={d: "date", v: "nav"}))
    return out


def merged(code: str) -> pd.DataFrame:
    """单位+累计合并表，附 diff=累计-单位（分红总额常数）"""
    unit, acc = nav_tables(code)
    m = unit.merge(acc, on="date", suffixes=("_u", "_a"))
    m["diff"] = (m["nav_a"] - m["nav_u"]).round(4)
    return m


def windiv(m: pd.DataFrame, lo: str, hi: str = END) -> float:
    """(lo, hi] 窗内分红现金总额：diff 的增量之和"""
    w = m[(m["date"] > lo) & (m["date"] <= hi)]
    chg = w["diff"].diff().fillna(0)
    return float(chg[chg != 0].sum())


print("=" * 108)
print(f"一、基金区间收益（单位净值+窗内分红现金修正口径）｜基线：09-18 回调起点 / 10-16 上次核查")
print("=" * 108)
rows = []
for code, name in FUNDS.items():
    try:
        m = merged(code)
        last = m.iloc[-1]

        def px(dt):
            s = m[m["date"] <= dt]
            return s.iloc[-1]["nav_u"] if len(s) else None

        b1, b2, ys = px(BASE_0918), px(BASE_1016), px("2025-12-31")
        d_0918, d_ytd = windiv(m, BASE_0918), windiv(m, "2025-12-31")
        r_0918 = (last["nav_u"] + d_0918) / b1 - 1 if b1 else None
        r_1016 = last["nav_u"] / b2 - 1 if b2 else None          # 10-16 以来无分红，单位净值即精确
        r_ytd = (last["nav_u"] + d_ytd) / ys - 1 if ys else None
        tail = m[m["date"] > BASE_0918]["nav_u"] + d_0918 * 0    # 窗内回撤：分红不在 09-18 后，单位净值即可
        mdd = ((tail / tail.cummax()) - 1).min() * 100 if len(tail) > 1 else 0.0
        rows.append({
            "代码": code, "名称": name, "净值日": str(last["date"].date()), "单位净值": round(last["nav_u"], 4),
            "自09-18%": round(r_0918 * 100, 2) if r_0918 is not None else None,
            "自10-16%": round(r_1016 * 100, 2) if r_1016 is not None else None,
            "YTD%(现金修正)": round(r_ytd * 100, 2) if r_ytd is not None else None,
            "09-18后最大回撤%": round(mdd, 2),
            "窗内分红": round(d_0918, 3),
        })
    except Exception as e:
        rows.append({"代码": code, "名称": name, "err": f"{type(e).__name__}: {str(e)[:70]}"})
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 108)
print("二、基准与光模块个股（新浪源）")
print("=" * 108)
for sym, name in [("sh000300", "沪深300"), ("sh000852", "中证1000"), ("sh000688", "科创50")]:
    try:
        df = ak.stock_zh_index_daily(symbol=sym)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] <= END].reset_index(drop=True)
        last = df.iloc[-1]
        b1 = df[df["date"] <= BASE_0918].iloc[-1]
        b2 = df[df["date"] <= BASE_1016].iloc[-1]
        ys = df[df["date"] < YEAR_START].iloc[-1]
        print(f"{name}: 截至 {last['date'].date()} 收盘 {last['close']:.2f} | "
              f"自09-18 {(last['close']/b1['close']-1)*100:+.2f}% | 自10-16 {(last['close']/b2['close']-1)*100:+.2f}% | "
              f"YTD {(last['close']/ys['close']-1)*100:+.2f}%")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__}: {str(e)[:80]}")

print()
print("光模块 20 日线信号（等信号清单③）：")
for sym, name in [("sz300308", "中际旭创"), ("sz300502", "新易盛")]:
    try:
        df = ak.stock_zh_a_daily(symbol=sym)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] <= END].reset_index(drop=True)
        last = df.iloc[-1]
        ma20 = df["close"].tail(20).mean()
        ma20_prev = df["close"].iloc[-25:-5].mean()
        b1 = df[df["date"] <= BASE_0918].iloc[-1]
        b2 = df[df["date"] <= BASE_1016].iloc[-1]
        above = "站上" if last["close"] >= ma20 else "仍低于"
        slope = "上行" if ma20 > ma20_prev else "仍下行"
        print(f"{name}: 截至 {last['date'].date()} 收盘 {last['close']:.2f} | {above} MA20（{ma20:.2f}，{slope}）| "
              f"自09-18 {(last['close']/b1['close']-1)*100:+.1f}% | 自10-16 {(last['close']/b2['close']-1)*100:+.1f}%")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__}: {str(e)[:80]}")

print()
print("=" * 108)
print("三、三季报披露情况（前十大重仓报告期，等信号清单①）")
print("=" * 108)
for code in ("000390", "011369", "022364", "004195", "012920"):
    name = FUNDS[code]
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date="2026")
        periods = sorted(df["季度"].unique()) if "季度" in df.columns else []
        latest = df[df["季度"] == periods[-1]] if periods else df.head(0)
        tops = "、".join(latest["股票名称"].head(5).tolist()) if len(latest) else ""
        print(f"{code} {name}: 报告期 {periods[-1] if periods else '?'} | 前五: {tops}")
    except Exception as e:
        print(f"{code} {name}: FAIL {type(e).__name__}: {str(e)[:70]}")

print()
print("=" * 108)
print("四、000390 分红差值核对（窗口：2026-06 以来）")
print("=" * 108)
try:
    m = merged("000390")
    recent = m[m["date"] >= "2026-06-01"]
    changed = recent[recent["diff"].diff().fillna(0) != 0]
    if len(changed):
        print(changed[["date", "nav_a", "nav_u", "diff"]].to_string(index=False))
    else:
        print("  6 月以来无新增分红事件")
    print(f"最新（{m.iloc[-1]['date'].date()}）：差值 {m.iloc[-1]['diff']}（应稳定≈3.078；此常数仅用于核对分红，不进区间收益）")
except Exception as e:
    print(f"FAIL {type(e).__name__}: {str(e)[:90]}")

print()
print("=" * 108)
print("五、申购状态（东财申购一览表，若接口可用）")
print("=" * 108)
try:
    purch = ak.fund_purchase_em()
    codes = {"022364", "000390", "011369", "004195", "012920"}
    hit = purch[purch["基金代码"].astype(str).isin(codes)]
    cols = [c for c in ["基金代码", "基金简称", "申购状态", "最低申购金额", "每日最大申购金额", "状态说明"] if c in purch.columns]
    print(hit[cols].to_string(index=False) if len(hit) else "  未取到（接口无返回或字段变动）")
except Exception as e:
    print(f"  FAIL {type(e).__name__}: {str(e)[:90]}（沿用 10-17 已知：012920 暂停申购；华商三只限购 1000 元/日）")
