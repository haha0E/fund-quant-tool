"""技术选型验证脚本：akshare 关键字段可得性 + 与库内净值交叉核对。

只读不写，运行：uv run python scripts/tech_probe_akshare.py
"""
import akshare as ak
import pandas as pd

pd.set_option("display.width", 200)
print(f"akshare 版本: {ak.__version__}\n")


def check(name: str, fn):
    try:
        df = fn()
        print(f"[PASS] {name}: {len(df)} 行, 列={list(df.columns)[:8]}")
        print(df.head(2).to_string(index=False))
        print()
        return df
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__}: {str(e)[:150]}\n")
        return None


# 1-2. 基金单位净值序列（普通 + QDII）
nav_390 = check("基金净值序列 000390 华商优势行业A",
                lambda: ak.fund_open_fund_info_em(symbol="000390", indicator="单位净值走势"))
check("基金净值序列 012920 易方达全球成长A (QDII)",
      lambda: ak.fund_open_fund_info_em(symbol="012920", indicator="单位净值走势"))

# 3. 基金档案（雪球源）
check("基金档案 000390", lambda: ak.fund_individual_basic_info_xq(symbol="000390"))

# 4. 前十大持仓（A 股基金 + QDII）
check("前十大持仓 000390 (2026)",
      lambda: ak.fund_portfolio_hold_em(symbol="000390", date="2026"))
check("前十大持仓 012920 QDII (2026)",
      lambda: ak.fund_portfolio_hold_em(symbol="012920", date="2026"))

# 5. 个股日线（前复权）
check("个股日线 300502 新易盛 前复权",
      lambda: ak.stock_zh_a_hist(symbol="300502", period="daily",
                                 start_date="20260901", end_date="20261013", adjust="qfq"))

# 6. 个股 PE/PB 历史序列 → 算近 5 年分位
ind = check("个股估值历史 300502 新易盛 (乐咕源)",
            lambda: ak.stock_a_indicator_lg(symbol="300502"))
if ind is not None:
    ind["trade_date"] = pd.to_datetime(ind["trade_date"])
    recent = ind[ind["trade_date"] >= ind["trade_date"].max() - pd.Timedelta(days=365 * 5)]
    cur_pe, cur_pb = recent.iloc[-1]["pe_ttm"], recent.iloc[-1]["pb"]
    pe_pct = (recent["pe_ttm"] <= cur_pe).mean() * 100
    pb_pct = (recent["pb"] <= cur_pb).mean() * 100
    print(f"  → [测算] 当前 PE(TTM)={cur_pe:.1f} 处近5年 {pe_pct:.0f} 分位; "
          f"PB={cur_pb:.1f} 处 {pb_pct:.0f} 分位\n")

# 7. 指数基准
check("指数日线 沪深300",
      lambda: ak.index_zh_a_hist(symbol="000300", period="daily",
                                 start_date="20260901", end_date="20261013"))

# 8. 基金排行（看分类粒度能否支撑领域筛选）
rank = check("基金排行(全部)", lambda: ak.fund_open_fund_rank_em(symbol="全部"))
if rank is not None:
    print(f"  → 分类字段取值: {rank['分类'] if '分类' in rank.columns else '无分类列'}\n")

# ===== 交叉核对：akshare 000390 净值 vs 项目内 Wind 口径周度 CSV =====
print("===== 交叉核对 akshare vs 库内 CSV（000390 单位净值） =====")
if nav_390 is not None:
    csv = pd.read_csv("data/000390_weekly_nav.csv", parse_dates=["date"])
    nav_390 = nav_390.rename(columns=lambda c: c.strip())
    date_col = [c for c in nav_390.columns if "日期" in c][0]
    nav_390[date_col] = pd.to_datetime(nav_390[date_col])
    samples = pd.concat([csv.head(2), csv.tail(3)])
    for _, row in samples.iterrows():
        week_end = row["date"]
        window = nav_390[(nav_390[date_col] <= week_end)
                         & (nav_390[date_col] > week_end - pd.Timedelta(days=7))]
        if len(window):
            ak_nav = float(window.iloc[-1][[c for c in nav_390.columns if "单位净值" in c][0]])
            diff_pct = abs(ak_nav - row["unit_nav"]) / row["unit_nav"] * 100
            print(f"  周标签 {week_end.date()}: CSV={row['unit_nav']:.3f} "
                  f"akshare={ak_nav:.3f} 偏差={diff_pct:.3f}% "
                  f"({'OK' if diff_pct <= 0.5 else '超阈值!'})")
        else:
            print(f"  周标签 {week_end.date()}: akshare 无对应数据")
