"""补充调查：指数基准（新浪源）+ 000390 分红核对。2026-10-15。只读不写。"""
import akshare as ak
import pandas as pd

BASE_DATE = "2026-09-18"

print("二(补)、指数基准（新浪源）")
for sym, name in [("sh000300", "沪深300"), ("sh000852", "中证1000"), ("sh000688", "科创50")]:
    try:
        df = ak.stock_zh_index_daily(symbol=sym)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] <= "2026-10-15"].reset_index(drop=True)
        last = df.iloc[-1]
        base = df[df["date"] <= BASE_DATE].iloc[-1]
        ys = df[df["date"] < "2026-01-01"].iloc[-1]
        r_since = (last["close"] / base["close"] - 1) * 100
        r_ytd = (last["close"] / ys["close"] - 1) * 100
        r_d20 = (last["close"] / df.iloc[-21]["close"] - 1) * 100
        r_d5 = (last["close"] / df.iloc[-6]["close"] - 1) * 100
        print(f"{name}: 截至 {last['date'].date()} 收盘 {last['close']:.2f} | "
              f"近5日 {r_d5:+.2f}% | 近20日 {r_d20:+.2f}% | 自09-18 {r_since:+.2f}% | YTD {r_ytd:+.2f}%")
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__}: {str(e)[:100]}")

print()
print("四(补)、000390 分红核对（累计-单位差值变动）")
unit = ak.fund_open_fund_info_em(symbol="000390", indicator="单位净值走势")
unit = unit.rename(columns=lambda c: c.strip())
u_d = [c for c in unit.columns if "日期" in c][0]
u_v = [c for c in unit.columns if "单位净值" in c][0]
unit = unit.rename(columns={u_d: "date", u_v: "nav"})
unit["date"] = pd.to_datetime(unit["date"])
unit["nav"] = pd.to_numeric(unit["nav"], errors="coerce")

acc = ak.fund_open_fund_info_em(symbol="000390", indicator="累计净值走势")
acc = acc.rename(columns=lambda c: c.strip())
a_d = [c for c in acc.columns if "日期" in c][0]
a_v = [c for c in acc.columns if "累计净值" in c][0]
acc = acc.rename(columns={a_d: "date", a_v: "acc"})
acc["date"] = pd.to_datetime(acc["date"])
acc["acc"] = pd.to_numeric(acc["acc"], errors="coerce")

m = unit.merge(acc[["date", "acc"]], on="date", how="inner")
m["diff"] = (m["acc"] - m["nav"]).round(4)
recent = m[m["date"] >= "2026-06-01"].reset_index(drop=True)
changed = recent[recent["diff"].diff().fillna(0) != 0]
print("2026-06 以来差值变动（=分红事件）：")
if len(changed):
    print(changed[["date", "acc", "nav", "diff"]].to_string(index=False))
else:
    print("  无变动")
print(f"最新（{m.iloc[-1]['date'].date()}）：单位 {m.iloc[-1]['nav']:.4f} / 累计 {m.iloc[-1]['acc']:.4f} / 差值 {m.iloc[-1]['diff']}")
print()
print("000390 近 8 周净值轨迹（周频采样）：")
weekly = m.set_index("date").resample("W-FRI").last().dropna(how="all").tail(9)
prev = None
for d, row in weekly.iterrows():
    chg = f"{(row['nav']/prev-1)*100:+.2f}%" if prev else "  —  "
    print(f"  {d.date()}  单位 {row['nav']:.4f}  周变动 {chg}")
    prev = row["nav"]
