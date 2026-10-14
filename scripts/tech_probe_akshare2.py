"""技术选型验证脚本 2：重试瞬态失败项 + 验证替代数据源。"""
import time

import akshare as ak
import pandas as pd

pd.set_option("display.width", 200)


def retry(name: str, fn, tries: int = 3, wait: float = 5.0):
    for i in range(tries):
        try:
            df = fn()
            print(f"[PASS] {name} (第{i + 1}次尝试): {len(df)} 行, 列={list(df.columns)[:9]}")
            print(df.head(3).to_string(index=False))
            print()
            return df
        except Exception as e:
            print(f"[重试{i + 1}] {name}: {type(e).__name__}: {str(e)[:100]}")
            time.sleep(wait)
    print(f"[FAIL] {name} 三次尝试后放弃\n")
    return None


# 1. 前十大持仓（重试 + 换年份兜底）
hold = retry("前十大持仓 000390 (2026)",
             lambda: ak.fund_portfolio_hold_em(symbol="000390", date="2026"))
if hold is None:
    hold = retry("前十大持仓 000390 (2025 兜底)",
                 lambda: ak.fund_portfolio_hold_em(symbol="000390", date="2025"))
retry("前十大持仓 012920 QDII (2026)",
      lambda: ak.fund_portfolio_hold_em(symbol="012920", date="2026"))

# 2. 个股日线：东财重试 + 新浪替代
hist = retry("个股日线 300502 东财源 前复权",
             lambda: ak.stock_zh_a_hist(symbol="300502", period="daily",
                                        start_date="20260901", end_date="20261013",
                                        adjust="qfq"))
if hist is None:
    retry("个股日线 300502 新浪源 前复权",
          lambda: ak.stock_zh_a_daily(symbol="sz300502", start_date="20260901",
                                      end_date="20261013", adjust="qfq"))

# 3. 个股估值：百度源（原乐咕个股接口已在 1.19.1 移除）
pe = retry("个股估值 300502 百度源 PE(TTM)",
           lambda: ak.stock_zh_valuation_baidu(symbol="300502", indicator="市盈率(TTM)",
                                               period="近五年"))
pb = retry("个股估值 300502 百度源 PB",
           lambda: ak.stock_zh_valuation_baidu(symbol="300502", indicator="市净率",
                                               period="近五年"))
for tag, df in [("PE(TTM)", pe), ("PB", pb)]:
    if df is not None:
        val_col = df.columns[-1]
        cur = float(df.iloc[-1][val_col])
        pct = (df[val_col].astype(float) <= cur).mean() * 100
        print(f"  → [测算] 300502 当前{tag}={cur:.1f}，处近5年 {pct:.0f} 分位")
print()

# 4. 指数基准：东财重试 + 新浪替代
idx = retry("指数日线 沪深300 东财源",
            lambda: ak.index_zh_a_hist(symbol="000300", period="daily",
                                       start_date="20260901", end_date="20261013"))
if idx is None:
    retry("指数日线 沪深300 新浪源",
          lambda: ak.stock_zh_index_daily(symbol="sh000300"))
