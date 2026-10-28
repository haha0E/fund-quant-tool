"""字段→数据源映射 + 自动降级路由（实现方案 §1，学 Vibe-Trading 多源抽象）。

路由表是「口径回归」的受测对象（M2 验收第三条）：
- 指数/个股行情：主路新浪源——东财 push2 行情域 Windows 实测被反爬（ProxyError），
  **永不入路由**；乐咕接口已从 akshare 1.19.1 移除，估值走百度源。
- 东财 F10（持仓/资产配置/费率）：主路 curl_cffi TLS 指纹；akshare 版（普通
  requests 同一端点）作为降级备选。
- 基金净值/雪球档案：akshare 直连实测可用，无备选（漂移时靠 probe 报警）。

fetch(kind, **kw) 按序尝试路由，全部失败抛 RuntimeError——由调用方在界面
明确标注数据缺口，不静默造假。
"""
from __future__ import annotations

from . import akshare_client, curl_cffi_client

# kind -> 有序客户端链（主路在前，降级在后）
ROUTES: dict[str, list[str]] = {
    "nav":             ["akshare"],            # 基金净值（东财基金数据域）
    "profile_basic":   ["akshare"],            # 雪球档案
    "fund_names":      ["akshare"],            # 基金名录
    "holdings":        ["curl_cffi", "akshare"],  # 东财 F10 前十大持仓（TLS 指纹主路）
    "allocation":      ["curl_cffi"],          # 东财 F10 资产配置（股票仓位）
    "fees":            ["curl_cffi"],          # 东财 F10 费率
    # 行情域红线：指数/个股/估值全部避开东财 push2（反爬实测）
    "index_daily":     ["akshare_sina"],       # 指数日频（新浪）
    "stock_daily":     ["akshare_sina"],       # 个股日频（新浪，M4 穿透层用）
    "stock_valuation": ["akshare_baidu"],      # 个股估值（百度，乐咕已移除）
}

_CLIENTS = {
    "akshare": {
        "nav": akshare_client.fetch_nav,
        "profile_basic": akshare_client.fetch_profile_basic,
        "fund_names": akshare_client.fetch_fund_names,
        "holdings": lambda code, year: _akshare_holdings(code, year),  # 降级备选
    },
    "curl_cffi": {
        "holdings": curl_cffi_client.fetch_holdings,
        "allocation": curl_cffi_client.fetch_allocation,
        "fees": curl_cffi_client.fetch_fees,
    },
    "akshare_sina": {
        "index_daily": akshare_client.fetch_index_daily,
        "stock_daily": lambda symbol: _sina_stock_daily(symbol),
    },
    "akshare_baidu": {
        "stock_valuation": lambda symbol: _baidu_valuation(symbol),
    },
}


def _akshare_holdings(code: str, year: str) -> list[dict]:
    """降级备选：akshare 版 jjcc（同端点、普通 requests，仅主路被拦时尝试）。"""
    import akshare as ak

    from . import net

    def do():
        df = ak.fund_portfolio_hold_em(symbol=code, date=year)
        out = []
        for _, r in df.iterrows():
            q = str(r.get("季度", ""))
            y = q[:4]
            qn = q[-2]
            rd = f"{y}-{int(qn) * 3:02d}-30" if y.isdigit() and qn.isdigit() else None
            if rd:
                out.append({"report_date": rd, "stock_code": str(r["股票代码"]),
                            "stock_name": str(r["股票名称"]),
                            "weight": float(str(r["占净值比例"]).replace("%", ""))})
        return out

    return net.retry(do, what=f"akshare holdings:{code}")


def _sina_stock_daily(symbol: str) -> list[dict]:
    """个股日频（新浪，sz300502 形式）。M4 穿透层用，M2 仅注册路由。"""
    import akshare as ak

    from . import net

    def do():
        df = ak.stock_zh_a_daily(symbol=symbol, start_date="20200101", end_date="20991231")
        df["date"] = df["date"].astype(str)
        return [{"date": r["date"], "close": float(r["close"])} for _, r in df.iterrows()]

    return net.retry(do, what=f"sina stock:{symbol}")


def _baidu_valuation(symbol: str) -> list[dict]:
    """个股 PE/PB（百度源，乐咕已从 1.19.1 移除）。M4 用，M2 仅注册路由。"""
    import akshare as ak

    from . import net

    def do():
        pe = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市盈率(TTM)", period="全部")
        pb = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市净率", period="全部")
        pb_map = {str(r["date"]): float(r["value"]) for _, r in pb.iterrows()}
        return [{"date": str(r["date"]), "pe_ttm": float(r["value"]),
                 "pb": pb_map.get(str(r["date"]))} for _, r in pe.iterrows()]

    return net.retry(do, what=f"baidu valuation:{symbol}")


def fetch(kind: str, **kw):
    """按路由链取数：主路失败自动降级；全链失败抛 RuntimeError（缺口显式化）。"""
    if kind not in ROUTES:
        raise KeyError(f"未注册的数据种类: {kind}")
    errors = []
    for client_name in ROUTES[kind]:
        fn = _CLIENTS.get(client_name, {}).get(kind)
        if fn is None:
            continue
        try:
            return fn(**kw)
        except Exception as e:  # noqa: BLE001 降级路由吞掉单路异常，换下一路
            errors.append(f"{client_name}: {e}")
    raise RuntimeError(f"{kind} 全路由失败 -> " + " | ".join(errors) if errors
                       else f"{kind} 无可用客户端实现")
