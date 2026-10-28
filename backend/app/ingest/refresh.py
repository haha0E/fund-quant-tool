"""刷新编排（实现方案 §1 ingest/refresh.py）：时序即时 + 截面拉取 + 指标落库。

scope:
- nav       基金净值（含分红事件检测）
- profile   档案 20 字段（雪球档案 + F10 费率 + F10 资产配置）
- holdings  前十大持仓（当年，缺则回退上一年）
- metrics   由库内净值重算指标（不外呼）
- all       以上全部

数据缺口纪律：单项失败记入结果 summary 的 errors，不中断其他基金，
界面按缺口显式标注（不静默造假）。
"""
from __future__ import annotations

from datetime import date

from ..db import conn
from ..services.metrics import Series, compute_metrics, has_negative_diff_drift
from . import source_map

# M2 名单（docs/调查报告-重仓基金-20261017.md 附录定稿）：持仓 5 + 研究池 7
DEFAULT_POOL: list[tuple[str, str, str, str]] = [
    # (code, name, pool_type, domain_tags)
    ("022364", "永赢科技智选A", "holding", "AI算力"),
    ("000390", "华商优势行业混合A", "holding", "AI算力"),
    ("011369", "华商均衡成长混合A", "holding", "AI算力"),
    ("004195", "招商中证1000指数增强C", "holding", "宽基"),
    ("012920", "易方达全球成长精选混合A", "holding", "QDII"),
    ("021030", "汇添富港股通创新药联接A", "research", "医药"),
    ("006113", "汇添富创新医药混合A", "research", "医药"),
    ("001411", "诺安创新驱动混合A", "research", "AI算力"),
    ("110005", "易方达积极成长混合", "research", "AI算力"),
    ("020972", "易方达中证机器人ETF联接A", "research", "机器人"),
    ("018344", "华夏中证机器人ETF联接A", "research", "机器人"),
    ("000960", "", "research", "医药"),  # 名字由名录接口补齐
]

_XQ_TO_COLUMN = {
    "基金名称": "name", "基金全称": "full_name", "基金类型": "fund_type",
    "成立时间": "inception_date", "最新规模": "scale", "基金公司": "company",
    "基金经理": "manager", "托管银行": "custodian", "基金评级": "rating",
    "业绩比较基准": "benchmark", "投资目标": "objective", "投资策略": "strategy",
    "跟踪标的": "tracked_index",
}


def seed_default_pool() -> dict:
    """12 只名单入池（幂等权威写：名字/池别/标签以定稿名单为准，created_at 保留）。

    背景：库里可能有 M1 期手工测试行（如 000390 曾录为 research），
    名单来自调查报告附录 A 定稿，故对本 12 只做全字段对齐而非只补空。
    """
    try:
        names = source_map.fetch("fund_names")
    except Exception:  # noqa: BLE001 名录拉不到不阻塞（名字可由档案回填）
        names = {}
    inserted, patched = [], []
    with conn() as c:
        for code, name, pool, tags in DEFAULT_POOL:
            name = name or names.get(code, "")
            exists = c.execute("SELECT name, pool_type, domain_tags FROM fund WHERE code = ?",
                               (code,)).fetchone()
            c.execute(
                """INSERT INTO fund (code, name, pool_type, domain_tags) VALUES (?, ?, ?, ?)
                   ON CONFLICT(code) DO UPDATE SET
                       name = CASE WHEN excluded.name = '' THEN fund.name ELSE excluded.name END,
                       pool_type = excluded.pool_type,
                       domain_tags = excluded.domain_tags""",
                (code, name, pool, tags))
            (inserted if not exists else patched).append(code)
    return {"inserted": inserted, "patched": patched}


def _detect_dividends(rows: list[dict]) -> list[dict]:
    """分红事件：累计-单位差值变动（§6 分红处理）。

    完整性纪律（110005 教训，2026-10-28 实测）：差值序列一旦出现**负向**变动
    （份额折算/数据修正），说明该基金 acc-unit 数据完整性已破——此时差值的
    正向日间跳动也全是噪声（实测会把振荡累成 5 元假分红，1 年收益虚到 +657%）。
    故：任一处负向变动 → 全序列 dividend=0 + 单条汇总异常标记，指标层据此不采信。
    差值本身只作核对常数，绝不参与区间收益。
    """
    diffs = [round(r["acc_nav"] - r["unit_nav"], 4)
             for r in rows if r["acc_nav"] is not None]
    has_anomaly = has_negative_diff_drift(
        [r["acc_nav"] for r in rows], [r["unit_nav"] for r in rows])

    out, prev_diff = [], None
    for r in rows:
        div, note = 0.0, None
        if r["acc_nav"] is not None:
            diff = round(r["acc_nav"] - r["unit_nav"], 4)
            if prev_diff is not None and diff > prev_diff + 1e-9 and not has_anomaly:
                div = round(diff - prev_diff, 4)
            prev_diff = diff
        out.append(dict(r, dividend=div, anomaly=note))
    if has_anomaly and out:
        out[-1]["anomaly"] = ("差值序列存在负向变动：分红推断与指标全序列不采信"
                              "（份额折算或数据修正，110005 先例）")
    return out


def refresh_nav(code: str) -> dict:
    rows = _detect_dividends(source_map.fetch("nav", code=code))
    with conn() as c:
        c.executemany(
            """INSERT INTO fund_nav (code, date, unit_nav, acc_nav, dividend)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(code, date) DO UPDATE
               SET unit_nav = excluded.unit_nav, acc_nav = excluded.acc_nav,
                   dividend = excluded.dividend""",
            [(code, r["date"], r["unit_nav"], r["acc_nav"], r["dividend"]) for r in rows],
        )
    anomalies = [f"{r['date']}: {r['anomaly']}" for r in rows if r["anomaly"]]
    return {"nav_rows": len(rows), "dividends": sum(1 for r in rows if r["dividend"] > 0),
            "anomalies": anomalies}


def refresh_profile(code: str) -> dict:
    basic = source_map.fetch("profile_basic", code=code)
    fees = source_map.fetch("fees", code=code)
    alloc = source_map.fetch("allocation", code=code)
    latest_alloc = next((a for a in alloc if a["stock_pct"] is not None), None)
    profile = {col: basic.get(src) for src, col in _XQ_TO_COLUMN.items()}
    profile.update(fees)
    profile["stock_position"] = latest_alloc["stock_pct"] if latest_alloc else None
    profile["stock_position_as_of"] = latest_alloc["report_date"] if latest_alloc else None
    profile["source"] = f"雪球档案 + 东财F10(费率/资产配置) @ {date.today().isoformat()}"
    with conn() as c:
        c.execute(
            """INSERT INTO fund_profile (code, as_of, name, full_name, fund_type,
                   inception_date, scale, company, manager, custodian, rating,
                   benchmark, objective, strategy, fee_management, fee_custody,
                   fee_subscription, fee_redemption, stock_position,
                   stock_position_as_of, tracked_index, source)
               VALUES (:code, :as_of, :name, :full_name, :fund_type, :inception_date,
                   :scale, :company, :manager, :custodian, :rating, :benchmark,
                   :objective, :strategy, :fee_management, :fee_custody,
                   :fee_subscription, :fee_redemption, :stock_position,
                   :stock_position_as_of, :tracked_index, :source)
               ON CONFLICT(code, as_of) DO UPDATE SET
                   name = excluded.name, full_name = excluded.full_name,
                   fund_type = excluded.fund_type, inception_date = excluded.inception_date,
                   scale = excluded.scale, company = excluded.company,
                   manager = excluded.manager, custodian = excluded.custodian,
                   rating = excluded.rating, benchmark = excluded.benchmark,
                   objective = excluded.objective, strategy = excluded.strategy,
                   fee_management = excluded.fee_management,
                   fee_custody = excluded.fee_custody,
                   fee_subscription = excluded.fee_subscription,
                   fee_redemption = excluded.fee_redemption,
                   stock_position = excluded.stock_position,
                   stock_position_as_of = excluded.stock_position_as_of,
                   tracked_index = excluded.tracked_index, source = excluded.source""",
            dict(profile, code=code, as_of=date.today().isoformat()),
        )
        # 档案名回填池表（空名或名录没补上的场景）
        if profile.get("name"):
            c.execute("UPDATE fund SET name = ? WHERE code = ? AND (name = '' OR name IS NULL)",
                      (profile["name"], code))
    missing = [k for k, v in profile.items()
               if v is None and k not in ("tracked_index", "rating", "objective", "strategy",
                                          "fee_redemption", "fee_subscription")]
    return {"missing_fields": missing}


def refresh_holdings(code: str) -> dict:
    this_year = str(date.today().year)
    rows = source_map.fetch("holdings", code=code, year=this_year)
    if not rows:  # 当年尚未披露 → 回退上一年（QDII/新发常见）
        rows = source_map.fetch("holdings", code=code, year=str(int(this_year) - 1))
    with conn() as c:
        c.executemany(
            """INSERT INTO fund_holding (code, report_date, stock_code, stock_name, weight)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(code, report_date, stock_code) DO UPDATE SET
                   stock_name = excluded.stock_name, weight = excluded.weight""",
            [(code, r["report_date"], r["stock_code"], r["stock_name"], r["weight"])
             for r in rows],
        )
    periods = sorted({r["report_date"] for r in rows})
    return {"holding_rows": len(rows), "report_periods": periods}


def refresh_metrics(code: str) -> dict:
    """纯库内计算，不外呼（services 层口径）。

    完整性闸门：差值负向漂移的基金（110005 先例）不算指标并清掉旧值，
    界面走 data_gaps 标注，不静默造假。
    """
    with conn() as c:
        rows = c.execute(
            "SELECT date, unit_nav, acc_nav, dividend FROM fund_nav WHERE code = ? ORDER BY date",
            (code,)).fetchall()
    if len(rows) < 2:
        return {"metric": None}
    if has_negative_diff_drift([r["acc_nav"] for r in rows],
                               [r["unit_nav"] for r in rows]):
        with conn() as c:
            c.execute("DELETE FROM fund_metric WHERE code = ?", (code,))
        return {"metric": None,
                "integrity": "差值负向漂移：指标不采信（份额折算/数据修正）"}
    m = compute_metrics(Series([r["date"] for r in rows],
                               [r["unit_nav"] for r in rows],
                               [r["dividend"] for r in rows]))
    if m.get("as_of") is None:
        return {"metric": None}
    with conn() as c:
        c.execute(
            """INSERT INTO fund_metric (code, as_of, ret_1m, ret_3m, ret_6m, ret_ytd,
                   ret_1y, ann_ret, max_dd, ann_vol, sharpe)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(code, as_of) DO UPDATE SET
                   ret_1m = excluded.ret_1m, ret_3m = excluded.ret_3m,
                   ret_6m = excluded.ret_6m, ret_ytd = excluded.ret_ytd,
                   ret_1y = excluded.ret_1y, ann_ret = excluded.ann_ret,
                   max_dd = excluded.max_dd, ann_vol = excluded.ann_vol,
                   sharpe = excluded.sharpe""",
            (code, m["as_of"], m.get("ret_1m"), m.get("ret_3m"), m.get("ret_6m"),
             m.get("ret_ytd"), m.get("ret_1y"), m.get("ann_ret"), m.get("max_dd"),
             m.get("ann_vol"), m.get("sharpe")))
    return {"metric": {k: m.get(k) for k in
                       ("as_of", "ret_1m", "ret_3m", "ret_6m", "ret_ytd", "ret_1y",
                        "ann_ret", "max_dd", "ann_vol", "sharpe")}}


_STEPS = {"nav": refresh_nav, "profile": refresh_profile, "holdings": refresh_holdings}


def refresh(scope: str = "all", codes: list[str] | None = None) -> dict:
    """编排入口。scope ∈ nav|profile|holdings|metrics|all；metrics 总在最后跑。"""
    wanted = list(_STEPS) if scope == "all" else [scope]
    steps = [s for s in wanted if s in _STEPS]  # metrics 不在 _STEPS，由下方单独处理
    with conn() as c:
        pool = c.execute("SELECT code FROM fund ORDER BY pool_type, code").fetchall()
    codes = codes or [r["code"] for r in pool]
    summary: dict = {"scope": scope, "funds": {}, "errors": {}}
    for code in codes:
        summary["funds"][code] = {}
        for step in steps:
            try:
                summary["funds"][code][step] = _STEPS[step](code)
            except Exception as e:  # noqa: BLE001 单项失败不阻塞其他基金
                summary["errors"][f"{code}:{step}"] = str(e)[:200]
    if scope in ("all", "metrics"):
        for code in codes:
            try:
                summary["funds"][code]["metrics"] = refresh_metrics(code)["metric"]
            except Exception as e:  # noqa: BLE001
                summary["errors"][f"{code}:metrics"] = str(e)[:200]
    return summary
