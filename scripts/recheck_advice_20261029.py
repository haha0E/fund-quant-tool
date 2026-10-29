"""10-29 三季报核查脚本（自动化任务）：三季报前十大 + 净值刷新 + 光模块 20 日线 + 基准。
只读不写。运行：uv run python -X utf8 scripts/recheck_advice_20261029.py
"""
import akshare as ak
import pandas as pd

pd.set_option("display.width", 240)

FUNDS = {
    "022364": "永赢科技智选A",
    "000390": "华商优势行业A",
    "011369": "华商均衡成长A",
    "004195": "招商中证1000增强C",
    "012920": "易方达全球成长精选A",
}
OPTICAL = {"中际旭创", "新易盛"}
BASE_0918 = "2026-09-18"
BASE_1020 = "2026-10-20"


def acc_nav_series(code: str) -> pd.DataFrame:
    df = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
    df = df.rename(columns=lambda c: c.strip())
    d = [c for c in df.columns if "日期" in c][0]
    v = [c for c in df.columns if "累计净值" in c][0]
    df[d] = pd.to_datetime(df[d])
    df[v] = pd.to_numeric(df[v], errors="coerce")
    return df.dropna(subset=[v]).reset_index(drop=True).rename(columns={d: "date", v: "nav"})


def px_at(df, date):
    idx = df.index[df["date"] <= date]
    return df.loc[idx[-1]] if len(idx) else None


print("=" * 110)
print("一、三季报披露与前十大持仓（对比 Q2，光模块=中际旭创/新易盛）")
print("=" * 110)
q3_tables = {}
for code, name in FUNDS.items():
    try:
        df = ak.fund_portfolio_hold_em(symbol=code, date="2026")
        df = df.rename(columns=lambda c: str(c).strip())
        qcol = "季度" if "季度" in df.columns else [c for c in df.columns if "季度" in c][0]
        periods = sorted(df[qcol].unique())
        q3_key = [p for p in periods if "3" in p.replace("三", "3")]
        q2_key = [p for p in periods if "2" in p.replace("二", "2")]
        q3 = df[df[qcol] == q3_key[-1]] if q3_key else df.head(0)
        q2 = df[df[qcol] == q2_key[-1]] if q2_key else df.head(0)
        q3_tables[code] = q3
        print(f"\n◆ {code} {name}｜报告期: {periods}")
        if len(q3):
            show_cols = [c for c in ["股票代码", "股票名称", "占净值比例", "持股数", "持仓变动"] if c in q3.columns]
            print(q3[show_cols].head(10).to_string(index=False))
            if len(q2):
                wcol = "占净值比例" if "占净值比例" in q3.columns else show_cols[2]
                for stock in OPTICAL:
                    q3w = q3.loc[q3["股票名称"] == stock, wcol]
                    q2w = q2.loc[q2["股票名称"] == stock, wcol]
                    q3v = float(str(q3w.iloc[0]).replace("%", "")) if len(q3w) else None
                    q2v = float(str(q2w.iloc[0]).replace("%", "")) if len(q2w) else None
                    if q3v is not None or q2v is not None:
                        mv = f"{q2v}→{q3v}" if q2v is not None else f"→{q3v}"
                        print(f"   [光模块] {stock}: Q2→Q3 占净值 {mv}")
        else:
            print("  三季报尚未取到（披露源未更新）")
    except Exception as e:
        print(f"\n◆ {code} {name}: FAIL {type(e).__name__}: {str(e)[:70]}")

print()
print("=" * 110)
print("二、净值刷新（累计净值口径）")
print("=" * 110)
rows = []
for code, name in FUNDS.items():
    try:
        df = acc_nav_series(code)
        last = df.iloc[-1]
        b1, b2 = px_at(df, BASE_0918), px_at(df, BASE_1020)
        ys = px_at(df, "2025-12-31")
        rows.append({
            "代码": code, "名称": name, "净值日": str(last["date"].date()), "累计净值": round(last["nav"], 4),
            "自09-18%": round((last["nav"]/b1["nav"]-1)*100, 2),
            "自10-20%": round((last["nav"]/b2["nav"]-1)*100, 2),
            "YTD%": round((last["nav"]/ys["nav"]-1)*100, 2),
        })
    except Exception as e:
        rows.append({"代码": code, "名称": name, "err": str(e)[:60]})
print(pd.DataFrame(rows).to_string(index=False))

print()
print("=" * 110)
print("三、光模块 20 日线（新浪源）")
print("=" * 110)
for sym, name in [("sz300308", "中际旭创"), ("sz300502", "新易盛")]:
    try:
        df = ak.stock_zh_a_daily(symbol=sym)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] <= "2026-10-29"].reset_index(drop=True)
        last = df.iloc[-1]
        ma20 = df["close"].tail(20).mean()
        ma20_prev = df["close"].iloc[-25:-5].mean()
        above = "站上" if last["close"] >= ma20 else "仍低于"
        slope = "上行" if ma20 > ma20_prev else "仍下行"
        print(f"{name}: 截至 {last['date'].date()} 收盘 {last['close']:.2f} | {above} MA20（{ma20:.2f}，{slope}）")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__}: {str(e)[:70]}")

print()
print("=" * 110)
print("四、基准（新浪源）")
print("=" * 110)
for sym, name in [("sh000300", "沪深300"), ("sh000852", "中证1000"), ("sh000688", "科创50")]:
    try:
        df = ak.stock_zh_index_daily(symbol=sym)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] <= "2026-10-29"].reset_index(drop=True)
        last = df.iloc[-1]
        b1 = df[df["date"] <= BASE_0918].iloc[-1]
        print(f"{name}: 截至 {last['date'].date()} {last['close']:.2f} | 自09-18 {(last['close']/b1['close']-1)*100:+.2f}%")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__}: {str(e)[:70]}")
