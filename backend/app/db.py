"""sqlite3 薄封装。v1 不引 ORM（实现方案 §3）：库表 DDL 全部集中在本文件。

Windows 纪律：连接强制 utf-8 路径与 text_factory 默认即可，但所有文件读写（md 导出、
快照导入）必须显式 encoding="utf-8"——控制台默认 GBK，不显式声明必踩。
"""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

# v1 全部建表语句集中于此（实现方案 §3 库表设计）
SCHEMA = """
CREATE TABLE IF NOT EXISTS fund (
    code        TEXT PRIMARY KEY,          -- 基金代码，如 000390
    name        TEXT NOT NULL,
    pool_type   TEXT NOT NULL CHECK (pool_type IN ('holding', 'research')),  -- 持仓/研究池
    domain_tags TEXT NOT NULL DEFAULT '',  -- 逗号分隔领域标签：AI,医药,黄金…
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS note (
    fund_code  TEXT PRIMARY KEY REFERENCES fund(code) ON DELETE CASCADE,
    content    TEXT NOT NULL DEFAULT '',   -- 手写结论层（markdown）
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- M2 摄取层落表：净值（含分红事件）/ 档案快照（保留历史 as_of）/ 指标 / 前十大持仓
CREATE TABLE IF NOT EXISTS fund_nav (
    code     TEXT NOT NULL REFERENCES fund(code) ON DELETE CASCADE,
    date     TEXT NOT NULL,               -- 净值日期 YYYY-MM-DD
    unit_nav REAL NOT NULL,               -- 单位净值（区间收益唯一口径，§6）
    acc_nav  REAL,                        -- 累计净值（仅作分红核对常数，禁入任何区间计算）
    dividend REAL NOT NULL DEFAULT 0,     -- 当日每份分红现金（累计-单位差值变动推得）
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS fund_profile (
    code                TEXT NOT NULL REFERENCES fund(code) ON DELETE CASCADE,
    as_of               TEXT NOT NULL,    -- 档案抓取日 YYYY-MM-DD（保留历史快照）
    name                TEXT,             -- 基金名称
    full_name           TEXT,             -- 基金全称
    fund_type           TEXT,             -- 基金类型（混合型-灵活配置…）
    inception_date      TEXT,             -- 成立日期
    scale               TEXT,             -- 最新规模（原文，如 94.68亿）
    company             TEXT,             -- 基金公司
    manager             TEXT,             -- 现任基金经理
    custodian           TEXT,             -- 托管银行
    rating              TEXT,             -- 基金评级
    benchmark           TEXT,             -- 业绩比较基准
    objective           TEXT,             -- 投资目标
    strategy            TEXT,             -- 投资策略（长文本）
    fee_management      REAL,             -- 管理费率 %/年
    fee_custody         REAL,             -- 托管费率 %/年
    fee_subscription    REAL,             -- 最高申购费率 %
    fee_redemption      REAL,             -- 最高赎回费率 %
    fee_sales_service   REAL,             -- 销售服务费率 %/年（C 类为主，M3 补字段）
    stock_position      REAL,             -- 股票占净值比 %（最新报告期）
    stock_position_as_of TEXT,            -- 股票仓位报告期
    tracked_index       TEXT,             -- 跟踪标的（联接/指数基金用，可空）
    source              TEXT,             -- 抓取来源与时间备注
    PRIMARY KEY (code, as_of)
);

CREATE TABLE IF NOT EXISTS fund_metric (
    code      TEXT NOT NULL REFERENCES fund(code) ON DELETE CASCADE,
    as_of     TEXT NOT NULL,              -- 净值截止日
    ret_1m    REAL, ret_3m REAL, ret_6m REAL, ret_ytd REAL, ret_1y REAL,  -- 区间收益（小数）
    ann_ret   REAL,                       -- 1 年窗口年化收益
    max_dd    REAL,                       -- 近 1 年最大回撤（窗内分红重构后）
    ann_vol   REAL,                       -- 年化波动率（日收益 std×√252）
    sharpe    REAL,                       -- (年化收益-2%)/年化波动
    PRIMARY KEY (code, as_of)
);

CREATE TABLE IF NOT EXISTS fund_holding (
    code        TEXT NOT NULL REFERENCES fund(code) ON DELETE CASCADE,
    report_date TEXT NOT NULL,            -- 报告期，如 2026-09-30
    stock_code  TEXT NOT NULL,
    stock_name  TEXT,
    weight      REAL,                     -- 占净值比例 %
    PRIMARY KEY (code, report_date, stock_code)
);

-- M1 遗留补齐（实现方案 §3）：份额/市值后续由 UI 录入，不阻塞 M2
CREATE TABLE IF NOT EXISTS my_position (
    code         TEXT PRIMARY KEY REFERENCES fund(code) ON DELETE CASCADE,
    shares       REAL,                    -- 持有份额
    market_value REAL,                    -- 市值快照（元）
    value_as_of  TEXT,                    -- 快照日期
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- M3 组合评估：基准指数日频（新浪路由，价格指数未含股息）
CREATE TABLE IF NOT EXISTS index_daily (
    code  TEXT NOT NULL,                  -- 新浪指数代码，如 sh000300
    date  TEXT NOT NULL,
    close REAL NOT NULL,
    PRIMARY KEY (code, date)
);
"""

# CREATE TABLE IF NOT EXISTS 不会给既有表补列——轻量迁移在此幂等执行
_MIGRATIONS = [
    ("fund_profile", "fee_sales_service",
     "ALTER TABLE fund_profile ADD COLUMN fee_sales_service REAL"),
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    # WAL：生产态 uvicorn 与脚本/调试进程可能并行读写，WAL 让读不阻塞写
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def conn():
    c = get_conn()
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        for table, column, ddl in _MIGRATIONS:
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                c.execute(ddl)
