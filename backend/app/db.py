"""sqlite3 薄封装。v1 不引 ORM（实现方案 §3）：库表 DDL 全部集中在本文件。

Windows 纪律：连接强制 utf-8 路径与 text_factory 默认即可，但所有文件读写（md 导出、
快照导入）必须显式 encoding="utf-8"——控制台默认 GBK，不显式声明必踩。
"""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

# v1 全部建表语句集中于此；M2 起随摄取层逐表补充（fund_nav/fund_holding 等，见实现方案 §3）
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
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
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
