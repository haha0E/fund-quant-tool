"""akshare 客户端（锁版本 1.19.1）：基金净值 / 雪球档案 / 基金名录 / 新浪指数。

Windows 实测结论（2026-10 探针）：东财基金数据域（fund_open_fund_info_em）可用；
东财 push2 行情域被反爬 → 指数/个股一律新浪源、估值百度源，本模块只承担新浪侧。
反爬纪律（sleep/退避/当日缓存）统一在 net.py 单点执行。
"""
from __future__ import annotations

import pandas as pd
import akshare as ak

from . import net


def _norm_col(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=lambda c: str(c).strip())


def fetch_nav(code: str) -> list[dict]:
    """单位+累计净值（东财基金数据域）。返回 [{date, unit_nav, acc_nav}]（升序）。

    累计净值只作分红核对常数（§6）：分红事件由 acc-unit 差值变动推得，
    在 refresh 编排层写入 fund_nav.dividend，绝不参与区间收益计算。
    """
    def do():
        unit = _norm_col(ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势"))
        acc = _norm_col(ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势"))
        ud = [c for c in unit.columns if "日期" in c][0]
        uv = [c for c in unit.columns if "单位净值" in c][0]
        ad = [c for c in acc.columns if "日期" in c][0]
        av = [c for c in acc.columns if "累计净值" in c][0]
        u = unit[[ud, uv]].copy()
        u.columns = ["date", "unit_nav"]
        a = acc[[ad, av]].copy()
        a.columns = ["date", "acc_nav"]
        for df, col in ((u, "unit_nav"), (a, "acc_nav")):
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df[col] = pd.to_numeric(df[col], errors="coerce")
        m = u.merge(a, on="date", how="left").dropna(subset=["unit_nav"])
        return [
            {"date": r["date"], "unit_nav": round(float(r["unit_nav"]), 4),
             "acc_nav": None if pd.isna(r["acc_nav"]) else round(float(r["acc_nav"]), 4)}
            for _, r in m.iterrows()
        ]

    return net.retry(do, what=f"akshare nav:{code}")


def fetch_profile_basic(code: str) -> dict:
    """雪球档案（fund_individual_basic_info_xq）：item/value 对 → dict。"""
    def do():
        df = ak.fund_individual_basic_info_xq(symbol=code)
        return {str(r["item"]).strip(): (None if pd.isna(r["value"]) else str(r["value"]).strip())
                for _, r in df.iterrows()}

    return net.cached("xq_profile", code,
                      lambda: net.retry(do, what=f"akshare profile:{code}"))


def fetch_index_daily(symbol: str) -> list[dict]:
    """指数日频收盘（新浪源，如 sh000300）。东财 push2 被反爬，禁入路由。"""
    def do():
        df = ak.stock_zh_index_daily(symbol=symbol)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return [{"date": r["date"], "close": float(r["close"])}
                for _, r in df.dropna(subset=["close"]).iterrows()]

    return net.retry(do, what=f"akshare index:{symbol}")


def fetch_fund_names() -> dict[str, str]:
    """全基金名录 code→name（一次外呼，入池播种名字用）。"""
    def do():
        df = ak.fund_name_em()
        code_col = df.columns[0]
        name_col = [c for c in df.columns if "名称" in str(c)][0]
        return {str(r[code_col]).strip(): str(r[name_col]).strip()
                for _, r in df.iterrows()}

    return net.cached("fund_names", "all",
                      lambda: net.retry(do, what="akshare fund_names"))
