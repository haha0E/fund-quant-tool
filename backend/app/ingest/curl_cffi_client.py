"""curl_cffi 客户端：东财基金 F10（TLS 指纹伪装）——前十大持仓 / 资产配置 / 费率。

Windows 实测：fundf10.eastmoney.com 对普通 requests 做反爬（背景事实），
curl_cffi impersonate="chrome" 实测可通（2026-10-28 探针：jjcc/zcpz/jjfl 均 200）。
反爬纪律（sleep/退避/当日缓存）统一在 net.py 单点执行。
"""
from __future__ import annotations

import random
import re

from bs4 import BeautifulSoup
from curl_cffi import requests as cr

from . import net

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")


def _get(url: str, referer: str, *, xhr: bool = False) -> str:
    def do():
        headers = {"Referer": referer, "User-Agent": _UA,
                   "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        if xhr:
            headers["X-Requested-With"] = "XMLHttpRequest"
        r = cr.get(url, impersonate="chrome", timeout=30, headers=headers)
        r.raise_for_status()
        if len(r.text) < 50:
            raise RuntimeError(f"东财 F10 返回过短({len(r.text)}字节)，疑被拦")
        return r.text

    return net.retry(do, what=f"eastmoney {url.split('?')[0].split('/')[-1]}")


def _qtr_to_date(label: str) -> str | None:
    """「2026年3季度」→ 2026-09-30（标签里若带显式日期则优先）。"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", label)
    if m:
        return m.group(0)
    m = re.search(r"(\d{4})年(\d)季度", label)
    if m:
        return f"{m.group(1)}-{int(m.group(2)) * 3:02d}-{30:02d}"
    return None


def fetch_holdings(code: str, year: str) -> list[dict]:
    """前十大持仓（东财 F10 jjcc，当年各季度）。返回 [{report_date, stock_code, stock_name, weight}]。

    weight=占净值比例%（东财原表即此口径）；报告期如 2026-09-30。
    """
    url = (f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code={code}"
           f"&topline=10&year={year}&month=&rt={random.random():.16f}")

    def parse() -> list[dict]:
        text = _get(url, f"https://fundf10.eastmoney.com/ccmx_{code}.html", xhr=True)
        m = re.search(r"apidata=\s*\{\s*content:\s*\"(.*)\",\s*arryear", text, re.S)
        html = (m.group(1) if m else text).replace("\\/", "/").replace("\\'", "'")
        soup = BeautifulSoup(html, features="lxml")
        rows: list[dict] = []
        for block in soup.find_all("div", class_="boxitem"):
            h4 = block.find("h4", class_="t")
            report_date = _qtr_to_date(h4.get_text(" ", strip=True) if h4 else "")
            if not report_date:
                continue
            for tr in block.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                if len(cells) < 4 or not cells[1] or cells[1] == "---":
                    continue
                if not re.fullmatch(r"[0-9A-Za-z.:]{1,12}", cells[1]):
                    continue  # A股6位数字；QDII 港股5位/美股 ticker
                # 表头跨列时空单元格占位（实测 2026-10：行内首个百分数格才是占净值比）
                pct_cells = [c for c in cells if re.fullmatch(r"\d+(\.\d+)?%", c)]
                if not pct_cells:
                    continue
                rows.append({"report_date": report_date, "stock_code": cells[1],
                             "stock_name": cells[2], "weight": float(pct_cells[0][:-1])})
        return rows

    return net.cached("f10_holdings", f"{code}_{year}", parse)


def fetch_allocation(code: str) -> list[dict]:
    """资产配置（F10 zcpz 页内嵌表）。返回 [{report_date, stock_pct, bond_pct, cash_pct, net_asset}]（降序）。

    stock_pct=股票占净值比%，net_asset=期末净资产（亿元）。
    """
    def parse() -> list[dict]:
        text = _get(f"https://fundf10.eastmoney.com/zcpz_{code}.html",
                    "https://fundf10.eastmoney.com/")
        soup = BeautifulSoup(text, features="lxml")
        table = next((t for t in soup.find_all("table")
                      if t.find("th") and "股票占净比" in t.get_text()), None)
        if not table:
            return []
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) < 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0] or ""):
                continue

            def num(s: str) -> float | None:
                s = s.replace("%", "").replace(",", "").strip()
                try:
                    return float(s)
                except ValueError:
                    return None  # '---' 等占位 → 数据缺口显式为 None

            rows.append({"report_date": cells[0], "stock_pct": num(cells[1]),
                         "bond_pct": num(cells[2]), "cash_pct": num(cells[3]),
                         "net_asset": num(cells[4])})
        return rows

    return net.cached("f10_alloc", code, parse)


def fetch_fees(code: str) -> dict:
    """费率（F10 jjfl 页）：管理/托管/申购（前端最高档）/赎回（最高档），单位 %。

    C 类无申购费、部分基金页缺表 → 对应键为 None（界面标注缺口，不造 0）。
    """
    def parse() -> dict:
        text = _get(f"https://fundf10.eastmoney.com/jjfl_{code}.html",
                    "https://fundf10.eastmoney.com/")
        soup = BeautifulSoup(text, features="lxml")
        out: dict = {"fee_management": None, "fee_custody": None,
                     "fee_subscription": None, "fee_redemption": None}
        for h4 in soup.find_all("h4", class_="t"):
            title = re.sub(r"\s+", " ", h4.get_text(strip=True))
            table = h4.find_next("table")
            if not table:
                continue
            body = table.get_text(" ", strip=True)
            if title == "运作费用":
                for key, kw in (("fee_management", "管理费"), ("fee_custody", "托管费")):
                    m = re.search(rf"{kw}[^\d]*([\d.]+)%", body)
                    if m:
                        out[key] = float(m.group(1))
            elif title.startswith("申购费率"):  # 实测标题无「（前端）」后缀，C 类可能整节缺失
                pcts = [float(x) for x in re.findall(r"([\d.]+)%", body)]
                out["fee_subscription"] = max(pcts) if pcts else None
            elif title == "赎回费率":
                pcts = [float(x) for x in re.findall(r"([\d.]+)%", body)]
                out["fee_redemption"] = max(pcts) if pcts else None
        return out

    return net.cached("f10_fees", code, parse)
