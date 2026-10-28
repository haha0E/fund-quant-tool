"""口径回归三：新浪降级路由（实现方案 §5 风险缓冲 + 调查报告 2026-10-17 §五）。

铁律：东财 push2 行情域 Windows 实测被反爬（ProxyError）——指数/个股行情
一律新浪源、估值百度源，东财行情永不入路由；东财 F10（持仓/费率）走
curl_cffi TLS 指纹主路。
"""
from app.ingest import akshare_client, curl_cffi_client
from app.ingest.source_map import ROUTES, fetch


def test_index_and_stock_quotes_routed_to_sina_never_push2():
    """行情域红线：指数/个股 → 新浪，路由链中不得出现任何东财行情客户端。"""
    assert ROUTES["index_daily"] == ["akshare_sina"]
    assert ROUTES["stock_daily"] == ["akshare_sina"]
    assert ROUTES["stock_valuation"] == ["akshare_baidu"]
    for kind in ("index_daily", "stock_daily", "stock_valuation"):
        assert all("push2" not in c.lower() and "east" not in c.lower()
                   for c in ROUTES[kind]), f"{kind} 路由泄漏东财: {ROUTES[kind]}"


def test_holdings_primary_curl_cffi_with_akshare_fallback():
    """F10 持仓：curl_cffi TLS 指纹主路 + akshare 同端点降级备选。"""
    assert ROUTES["holdings"][0] == "curl_cffi"
    assert ROUTES["holdings"] == ["curl_cffi", "akshare"]


def test_fetch_unknown_kind_and_route_degradation():
    """未注册 kind 报 KeyError；路由表内每个 kind 都有可用客户端实现。"""
    try:
        fetch("nonexistent_kind")
        raised = False
    except KeyError:
        raised = True
    assert raised
    # 静态路由健全性：holdings/allocation/fees/nav/profile 均可解析到实现
    from app.ingest.source_map import _CLIENTS, ROUTES as R
    for kind, chain in R.items():
        assert any(c in _CLIENTS and kind in _CLIENTS[c] for c in chain), \
            f"{kind} 全链无实现: {chain}"


def test_anti_crawl_discipline_present():
    """反爬纪律单点：两个客户端都必须经过 net（sleep/退避/当日缓存）。"""
    import inspect
    from app.ingest import net
    src = inspect.getsource(akshare_client)
    assert "net.retry" in src and "net.cached" in src
    src = inspect.getsource(curl_cffi_client)
    assert "net.retry" in src or "_get(" in src  # curl 侧经 _get → net.retry
    assert net.CALL_INTERVAL >= 0.5 and net._MAX_TRIES >= 3
