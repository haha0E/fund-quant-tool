"""重新调查脚本（2026-10-15）：持仓 5 只 + 当时推荐候选 6 只的最新表现。
对比基线：investment-weekly 第 4 期周报（业绩截止 2026-09-18 净值）。
只读不写。运行：uv run python scripts/recheck_advice_20261015.py
"""
import akshare as ak
import pandas as pd

pd.set_option("display.width", 220)

FUNDS = {
    # 持仓
    "022364": "永赢科技智选A",
    "000390": "华商优势行业A",
    "011369": "华商均衡成长A",
    "004195": "招商中证1000增强C",
    "012920": "易方达全球成长精选A",
    # 当时推荐候选
    "001411": "诺安创新驱动A(首推·存储设备)",
    "110005": "易方达积极成长(备选·设备)",
    "021030": "汇添富港股通创新药联接A(次选)",
    "006113": "汇添富创新医药A(A股替代)",
    "020972": "易方达机器人联接A(观察)",
    "018344": "华夏机器人联接A(观察)",
}
BASE_DATE = "2026-09-18"   # 第4期周报业绩截止
YEAR_START = "2026-01-01"


def nav_series(code: str) -> pd.DataFrame:
    df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    df = df.rename(columns=lambda c: c.strip())
    date_col = [c for c in df.columns if "日期" in c][0]
    nav_col = [c for c in df.columns if "单位净值" in c][0]
    df[date_col] = pd.to_datetime(df[date_col])
    df[nav_col] = pd.to_numeric(df[nav_col], errors="coerce")
    df = df.dropna(subset=[nav_col]).reset_index(drop=True)
    return df.rename(columns={date_col: "date", nav_col: "nav"})


print("=" * 100)
print("一、基金净值与区间收益（单位净值口径，000390 未计分红）")
print("=" * 100)
rows = []
for code, name in FUNDS.items():
    try:
        df = nav_series(code)
        last = df.iloc[-1]
        base_idx = df.index[df["date"] <= BASE_DATE]
        base = df.loc[base_idx[-1]] if len(base_idx) else None
        ys_idx = df.index[df["date"] < YEAR_START]
        ys = df.loc[ys_idx[-1]] if len(ys_idx) else None
        r_since = (last["nav"] / base["nav"] - 1) * 100 if base is not None else None
        r_ytd = (last["nav"] / ys["nav"] - 1) * 100 if ys is not None else None
        r_w1 = (last["nav"] / df.iloc[-6]["nav"] - 1) * 100 if len(df) >= 6 else None
        r_d20 = (last["nav"] / df.iloc[-21]["nav"] - 1) * 100 if len(df) >= 21 else None
        # 09-18 之后的最大回撤
        tail = df[df["date"] > BASE_DATE]
        mdd = 0.0
        if len(tail) > 1:
            cummax = tail["nav"].cummax()
            mdd = ((tail["nav"] / cummax) - 1).min() * 100
        rows.append({
            "代码": code, "名称": name, "最新日期": last["date"].date(), "单位净值": round(last["nav"], 4),
            "自09-18%": round(r_since, 2) if r_since is not None else None,
            "近5日%": round(r_w1, 2) if r_w1 is not None else None,
            "近20日%": round(r_d20, 2) if r_d20 is not None else None,
            "今年以来%": round(r_ytd, 2) if r_ytd is not None else None,
            "09-18后最大回撤%": round(mdd, 2) if mdd < 0 else 0.0,
        })
    except Exception as e:
        rows.append({"代码": code, "名称": name, "err": f"{type(e).__name__}: {str(e)[:80]}"})
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 100)
print("二、指数基准对照")
print("=" * 100)
for sym, name in [("000300", "沪深300"), ("000852", "中证1000"), ("000688", "科创50")]:
    try:
        df = ak.index_zh_a_hist(symbol=sym, period="daily", start_date="20260101", end_date="20261015")
        df = df.rename(columns=lambda c: str(c).strip())
        close_col = [c for c in df.columns if "收盘" in c][0]
        date_col = [c for c in df.columns if "日期" in c][0]
        df[date_col] = pd.to_datetime(df[date_col])
        df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
        last = df.iloc[-1]
        base = df[df["date"] <= BASE_DATE].iloc[-1]
        ys = df.iloc[0]
        r_since = (last[close_col] / base[close_col] - 1) * 100
        r_ytd = (last[close_col] / ys[close_col] - 1) * 100
        r_d20 = (last[close_col] / df.iloc[-21][close_col] - 1) * 100
        print(f"{name}: 最新 {last[date_col].date()} 收盘 {last[close_col]:.2f} | "
              f"自09-18 {r_since:+.2f}% | 近20日 {r_d20:+.2f}% | YTD {r_ytd:+.2f}%")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__}: {str(e)[:100]}")

print()
print("=" * 100)
print("三、三季报持仓是否已披露（前十大重仓报告期）")
print("=" * 100)
for code, name in FUNDS.items():
    if code not in ("022364", "000390", "011369", "004195", "012920"):
        continue
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date="2026")
        periods = sorted(df["季度"].unique()) if "季度" in df.columns else []
        latest = df[df["季度"] == periods[-1]] if periods else df.head(0)
        tops = "、".join(latest["股票名称"].head(5).tolist()) if len(latest) else ""
        print(f"{code} {name}: 报告期 {periods[-1] if periods else '?'} | 前五: {tops}")
    except Exception as e:
        print(f"{code} {name}: FAIL {type(e).__name__}: {str(e)[:80]}")

print()
print("=" * 100)
print("四、000390 分红口径补记（累计净值-单位净值差值变动）")
print("=" * 100)
try:
    acc = ak.fund_open_fund_info_em(symbol="000390", indicator="累计净值走势")
    acc = acc.rename(columns=lambda c: c.strip())
    dcol = [c for c in acc.columns if "日期" in c][0]
    acol = [c for c in acc.columns if "累计净值" in c][0]
    acc[dcol] = pd.to_datetime(acc[dcol])
    acc[acol] = pd.to_numeric(acc[acol], errors="coerce")
    unit = nav_series("000390")
    m = acc.merge(unit, on="date", how="inner").tail(30)
    m["差值"] = (m[acol] - m["nav"]).round(4)
    changed = m[m["差值"].diff().fillna(0) != 0]
    print("近30个净值日差值变动（=分红事件）：")
    print(changed[["date", acol, "nav", "差值"]].to_string(index=False) if len(changed) else "  无变动")
    print(f"最新差值: {m.iloc[-1]['差值']}（09-18 时点约 3.078，其中窗口前基数 2.33）")
except Exception as e:
    print(f"FAIL {type(e).__name__}: {str(e)[:100]}")
