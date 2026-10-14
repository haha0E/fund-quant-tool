# Windows 迁移交接文档（2026-10-14）

> 用途：从 macOS 迁移到 Windows 主机继续开发。新会话开工前先读本文 + `ROADMAP.md`（末尾进度记录）+ `docs/PRD-fund-workbench.md` + `docs/技术选型-fund-workbench.md`。

## 项目当前状态

- **生命周期**：需求调研 ✅ → 技术选型 ✅（文档定稿，待用户最终确认后关闭）→ **实现方案设计（下一阶段）** → 实现。
- **已定技术栈**：FastAPI + React + Ant Design + ECharts；SQLite 单库 + md 快照导出；数据层 akshare(1.19.1 锁版本) + curl_cffi 双客户端；截面数据由 ZCode 桌面定时自动化产出、经同步盘快照文件导入。
- **已验证**：数据可得性全闭环（scripts/tech_probe_akshare*.py），000390 净值与 Wind 口径交叉核对 5/5 点 0.000% 偏差；东财 push2 行情域反爬已绕开（个股走腾讯源、指数走新浪源、基金持仓走 curl_cffi）。

## Windows 环境搭建（按序执行）

```powershell
# 1. 安装 uv（PowerShell）
irm https://astral.sh/uv/install.ps1 | iex

# 2. 克隆并恢复环境（Python 3.12 由 uv 自动按 .python-version 处理）
git clone git@github.com:haha0E/fund-quant-tool.git
cd fund-quant-tool
uv sync

# 3. 【必做】上线首周数据源复测（macOS 验证 ≠ Windows 网络环境）
uv run python scripts/tech_probe_akshare.py
uv run python scripts/tech_probe_akshare2.py
# 预期：净值/档案/排行/估值/指数 PASS 且交叉核对偏差 ≤0.5%；若东财域失败属已知反爬，见选型文档 §2
```

## Windows 特别注意

1. 控制台默认 GBK：所有文件读写显式 `encoding="utf-8"`；PowerShell 可先 `chcp 65001`。
2. 定时任务用「任务计划程序」替代 cron；服务常驻用 NSSM 或开机自启脚本。
3. SSH key 需在 Windows 重新生成并添加到 GitHub（`ssh-keygen -t ed25519` → 添加公钥）。
4. `.env` 不入库：Windows 上手动重建，内容为 `TYPESAFE_API_KEY=...`（密钥见 macOS 原 ~/.zcode 相关配置或 console.typesafe.ai）。

## 下一阶段任务清单（实现方案设计）

1. **zvt spike（半天，第一件事）**：实测 zvt 基金净值/十大持仓是否开箱可用（调研结论见选型文档 §5.4）——决定数据层自建还是采用 zvt。
2. 模块划分 + 数据流图（含 Mac→Windows 截面快照链路：ZCode 桌面自动化 → 同步盘 CSV/JSON → Windows 端导入 SQLite）。
3. 里程碑与工作量估算（每周 6-10 小时预算）。
4. 项目骨架：backend/（FastAPI）+ frontend/（React+Vite+AntD+ECharts）。

## 上游数据自动化（留在 macOS 的部分）

- ZCode 桌面定时自动化（每周一）：刷新截面数据 → 快照落同步盘。Windows 迁移后此环节仍在装有 ZCode 的机器上跑；若彻底弃用 macOS，改走 akshare 兜底（质量降级，见 PRD/选型文档）。
