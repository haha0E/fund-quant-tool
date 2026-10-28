# 会话交接文档（2026-10-28 · M2 完成 → M3 待开工）

> 用途：新会话开工前先读本文 + `ROADMAP.md`（末尾进度行）+ `docs/实现方案-fund-workbench.md`（§1 架构 / §3 库表 / §5 里程碑 / §6 口径）+ `docs/复查报告-重仓基金-20261020.md` §四（口径反转教训）。
> 历史：本文原为 2026-10-14 Windows 迁移交接（uv/GitHub/数据源复测均已完成，详见 ROADMAP 10-14 行），现整体重写为 M2→M3 交接。

## 项目当前状态

- **进度**：M1 ✅（画像库 CRUD+结论双写）→ **M2 ✅（2026-10-28 验收线达成）** → M3 待开工（用户手机验收 M2 后，10-30 开工，11-17 前后交付）。
- **池状态**：持仓 4（000390/004195/012920/022364）+ 研究池 8（021030/006113/001411/110005/020972/018344/000960/**011369**——2026-10-28 已执行二选一卖出、转研究池作克隆对照，标签"AI算力,克隆对照"）。
- **投资侧待办**：卖出 011369 的资金去向未定（创新药定投 021030/006113 仅新钱，或暂持货币）；下次双周核查 **2026-11-11**。
- **运行时**：任务计划 FQT_Web_Server 常驻 `0.0.0.0:8000`（防火墙「FQT 8000 tailnet only」仅放行 100.64.0.0/10，已实测）；手机访问 `http://100.124.213.38:8000/`；前端 dist 由 FastAPI 同源托管。

## M2 交付物地图（2026-10-28，commit d8e1507/de3227b/e2822f4）

| 模块 | 文件 | 要点 |
|---|---|---|
| 摄取层 | `backend/app/ingest/`（net/source_map/akshare_client/curl_cffi_client/refresh） | 网络外呼唯一入口；net.py 反爬纪律单点（0.6s 间隔+指数退避+当日缓存 `data/cache/`，删当日目录=强制重拉）；source_map 路由红线：指数/个股→新浪、估值→百度、**东财 push2 永不入路由**；F10（持仓 jjcc/资产配置 zcpz/费率 jjfl）走 curl_cffi TLS 指纹，持仓表头跨列空占位→权重取"行内首个百分数格" |
| 计算层 | `backend/app/services/metrics.py` | §6 口径纯函数：区间收益现金分红口径、年化自算、窗内分红重构回撤、√252 波动、夏普 2% 无风险、`align_common_dates`（M3 直接复用）、`has_negative_diff_drift` 完整性闸门 |
| API | `routers/funds.py`（GET /{code} 详情+缺口标注）、`routers/refresh.py`（POST ?scope=&code=） | scope=metrics 已修 _STEPS KeyError；缺口显式 data_gaps 不造假 |
| 库表 | `db.py` | fund_nav（含 dividend 列）/fund_profile（20 字段）/fund_metric/fund_holding/my_position（M1 遗留 DDL 补齐）；WAL 已开 |
| 前端 | `pages/FundDetail.tsx`、`components/EChart.tsx` | **echarts-for-react@3.0.6 已弃用**（React18 StrictMode 下画布 0 宽/丢失），自写 EChart 封装（init/dispose/ResizeObserver）；App.tsx 全局包 TooltipProvider（Radix 必需）；画像库行点击进详情 |
| 测试 | `backend/tests/` 13 用例 | 口径三条：分红（现金口径/窗外忽略/累计阻尼护栏）/基准对齐（错位虚增 2pp）/新浪路由红线 |
| 脚本 | `scripts/m2_refresh.py`（播种+全刷）、`scripts/verify_m2.py`（验收自检） | 复跑：`uv run python scripts/verify_m2.py`、`cd backend && uv run python -m pytest tests/ -v` |

## 必须知道的事实与坑（M2 实测沉淀）

1. **110005 完整性闸门**：acc-unit 差值负向漂移（份额折算）→ 正向跳动全是噪声（曾累成 5 元假分红、1 年收益虚 +657%）→ 分红推断与指标**全序列不采信**，界面走 data_gaps。其它基金差值干净。
2. **000390 校验基准**：对 `data/000390_weekly_nav.csv` 156/157 行 0.000%；唯一偏差 2024-03-29（Wind 1.035 vs 东财 1.0360，官方 lsjz 复核东财自洽，真值疑 1.0355 舍入边界）。长假周核对用「≤周标签最后净值日」。
3. **000390 口径锚点**：2026-06-15 分红 0.463/份；差值常数 3.078；YTD = (1.679+0.463)/1.870−1 = +14.55%（截至 10-27）。
4. **021030 联接基金**无股票明细（只投目标 ETF），jjcc 返回空属真实披露缺口，界面已标注。
5. **Windows curl 传中文 JSON body 必坏**（GBK 管道）→ 一律用 python urllib/json 发请求。
6. **git push**：HTTPS 凭据已失效，用 SSH 一次性 URL `git push git@github.com:haha0E/fund-quant-tool.git main:main`。
7. **部署节律**：改前端 = `npm run build` 即生效（FileResponse 按请求读盘，无需重启）；改后端 = `MSYS_NO_PATHCONV=1 schtasks /end /tn FQT_Web_Server` → `/run`；本地调试另起 `uvicorn app.main:app --port 8010` 不碰生产。
8. 全量首刷约 2 分钟（反爬 sleep 为主），单基金 15-30 秒；重复调用走当日缓存不外呼。

## 已建自动化（本工作区）

- **双周策略会话**（automation-bb7eb9d5）：每 2 周周三 09:00，**首次 2026-11-11**。自动：读 workbench.db 生成 `data/strategy/brief-YYYYMMDD.md`（指标/持仓环比/光模块集中度/缺口）→ Bark 推送摘要 → git commit+push。用户有空时开 ZCode 会话敲 `/grill-me` 拷问策略（该技能 disable-model-invocation，只能用户触发）。

## 下一步：M3 范围（用户 2026-10-28 已确认扩展）

用户手机验收 M2（6 步清单：指标卡四数字/YTD 手算锚点/图表切窗/持仓滞后徽标/110005 不采信/刷新+结论保存）后，10-30 开工：

1. **my_position 录入 UI**（前置，半天）——M3 默认权重 = 份额×最新净值。
2. **预检入池**（约 1 天）：`GET /api/funds/preflight/{code}` 走 ingest 拉预览不入库；弹窗两步：输代码→预览卡→确认入池并单刷。
3. **结论自动草稿**（约 1 天）：`GET /api/funds/{code}/note/draft` 从库内确定性模板生成（指标+持仓环比+分红+缺口+规则化提示），填入编辑框不自动保存——**不用 LLM 生成底稿**（用户无量化基础，要可复算可信）。
4. **策略页 + data/strategy/**（约 1.5 天）：固化策略 md（从两份调查报告提炼：定投纪律/二选一框架/暴露上限/核查节奏）+ 前端只读渲染 + git diff 版本史。
5. **组合评估三件套 + 基准超额**（主体）：基准指数入库（index_daily 新浪路由已通）、services/portfolio.py（净值合成/相关性/超额，用 align_common_dates）、`POST /api/portfolio/eval`、前端组合页（等权/手调、热力图）。验收=§5 原文不降标准。
6. **token 鉴权**（半天，用户已同意）：写接口必带 token，手机存一次。
7. 顺手：C 类销售服务费字段；长窗（>1年）回撤改分红再投复权序列（修常数阻尼）。

M4 穿透 ~11 月底、M5 领域探索+快照+任务计划 ~12 月上中、M6 总验收 ~12 月下（重做 10-13 诊断 + 3 基金抽验 ≤0.5pct）。

## 红线（沿用，不因里程碑变化）

不动 8100/HQ；FQT_Web_Server 任务只 end/run 不改配置；不 bind 公网、不放宽 CORS；akshare 锁 1.19.1；不改 `data/` 已有文件（000390_weekly_nav.csv 是校验基准）；workbench.db、data/shots/、data/cache/ 不入 git；网络外呼只出现在 ingest/；数据缺口界面显式标注不造假；反爬纪律优先于进度。
