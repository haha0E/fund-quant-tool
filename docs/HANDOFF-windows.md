# 会话交接文档（2026-10-29 · M6 完成 —— ROADMAP 阶段 1（产品化 v1）全部收口）

> 用途：新会话开工前先读本文 + `ROADMAP.md`（末尾进度行）+ `docs/实现方案-fund-workbench.md`（§1 架构 / §3 库表 / §5 里程碑 / §6 口径）+ `docs/复查报告-重仓基金-20261020.md` §四（口径反转教训）。
> 历史：本文原为 2026-10-14 Windows 迁移交接（uv/GitHub/数据源复测均已完成，详见 ROADMAP 10-14 行），现整体重写为 M2→M3 交接。

## 项目当前状态

- **进度**：M1-M6 **全部 ✅（2026-10-29 收口）**——产品化 v1 完结：画像/组合/穿透/领域/策略/仪表盘六页全实装，34/34 测试 + verify_m2/4/5/6 全 PASS，生产常驻。下一步是阶段 2（实盘观察+策略演化），不再有开发里程碑。
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
11. 定时任务三件：FQT_Web_Server（常驻服务，只 end/run）、FQT_Weekly_Refresh（周一 09:30 全量刷）、FQT_Daily_Snapshot（每日 10:00 快照导入）；后两者脚本 scripts/cron_call.py，重装跑 setup_m5_tasks.ps1（幂等）。
8. 全量首刷约 2 分钟（反爬 sleep 为主），单基金 15-30 秒；重复调用走当日缓存不外呼；基准指数 scope=index 单独刷（两个指数各一次外呼）。
9. **手机写操作（入池/刷新/保存）需 token**：电脑打开 data/auth_token.txt 复制，手机首次操作弹窗粘贴一次（存 localStorage）；GET 不需要。
10. M2 的「指标卡四数字/YTD 锚点」等验收点全部不变；000390 YTD +14.55%（10-27）仍为锚点。

## 已建自动化（本工作区）

- **双周策略会话**（automation-bb7eb9d5）：每 2 周周三 09:00，**首次 2026-11-11**。自动：读 workbench.db 生成 `data/strategy/brief-YYYYMMDD.md`（指标/持仓环比/光模块集中度/缺口）→ Bark 推送摘要 → git commit+push。用户有空时开 ZCode 会话敲 `/grill-me` 拷问策略（该技能 disable-model-invocation，只能用户触发）。

## M3 交付物地图（2026-10-28 晚，21/21 测试绿 + 生产实测）

| 模块 | 文件 | 要点 |
|---|---|---|
| 性能修复 | `main.py`（GZipMiddleware+Cache-Control）、`EChart.tsx`（echarts 按需）、`vite.config.ts`（manualChunks） | 首屏传输 1.69MB→约 350KB（-79%）：>1KB 响应一律 gzip；assets/ immutable 缓存一年、index.html no-cache；echarts/zrender 独立 chunk（业务迭代零重下）。**「有时加载很久」根因 = 未压缩大 bundle × tailnet DERP 中继波动** |
| 持仓录入 | `routers/funds.py`（PUT/DELETE position）、FundDetail 持仓卡 | 市值=份额×最新单位净值自动算；组合权重默认=份额×净值占比 |
| 预检入池 | `routers/funds.py`（GET preflight/{code}）、FundLibrary 两步弹窗 | 走 ingest 拉档案+净值算预览（近1y/YTD 现金分红口径+完整性闸门）不入库；预览卡→确认入池并单刷；预检失败有手动录入逃生门 |
| 结论草稿 | `services/note_draft.py`、GET /{code}/note/draft、详情页按钮 | **确定性模板非 LLM**：基本面+指标+持仓环比（新进/退出/加减仓>0.5pp）+分红+缺口+规则提示（回撤-20%/夏普0/收益-10%/滞后120天）；填入编辑框不自动保存 |
| 策略页 | `data/strategy/strategy.md`、`routers/strategy.py`、Strategy.tsx（marked） | 固化策略（不做三件事/定投纪律/二选一框架/暴露上限≤60%/核查节奏/信号清单/口径红线）；strategy.md 置顶+brief-* 降序；修订走 git |
| 组合评估 | `db.py`（index_daily 表）、`services/portfolio.py`、`routers/portfolio.py`、Portfolio.tsx | scope=index 基准入库（沪深300/中证1000）；共同交易日对齐+日收益现金分红口径+每日再平衡合成；三权重模式（持仓份额/等权/手调）；两两 pearson 热力图；对齐后基准超额；完整性闸门成员 div 置 0+缺口标注 |
| token 鉴权 | `config.get_auth_token`、main.py 中间件、前端 TokenDialog | data/auth_token.txt 首访生成；/api 非 GET 必带 X-FQT-Token（GET 放行）；前端 401 全局弹窗，手机粘贴一次 |
| 顺手 | fund_profile.fee_sales_service（幂等迁移 _MIGRATIONS）、详情页长窗复权回撤 | C 类销售服务费；「全部」窗（>1年）回撤改分红再投复权因子 |

**M3 修掉的两个真 bug**（测试拦下，复述防再犯）：
1. `_member_daily_returns` 收益序列与共同日错位一天 → 组合净值整体错位（等权手算用例必红）；
2. 基准超额没用 align 后的序列，基金多出的尾日被计入超额（§6-6 铁律的组合版回归用例必红）。

## M4 交付物地图（2026-10-28 深夜）

| 模块 | 文件 | 要点 |
|---|---|---|
| 库表 | `db.py` | stock_daily（新浪 qfq 前复权日频）/stock_valuation（百度 PE/PB 序列，分位样本 2020 至今） |
| 摄取 | `ingest/refresh.py`（refresh_stocks）、`source_map.py`（_sina_stock_daily 加 qfq） | scope=stocks&symbols=，10 只约 12 秒（反爬 0.6s/次+当日缓存）；港股/美股无路由显式报错不算指标 |
| 计算 | `services/overlap.py` + `metrics.percentile_of_latest` | 穿透权重 Σ(基金权重×占净值比) 同名合并；未披露=1−Σ(权重×前十大合计)；有效持仓数 ≥1%；滞后按成员；个股 10 指标（3m/6m/YTD/52周位/波动/回撤/PE/PB/两分位） |
| API | `GET /api/portfolio/overlap?codes=&w=`、`POST /api/refresh?scope=stocks&symbols=` | 权重三模式（手调 w 参数/份额×净值/等权） |
| 前端 | `pages/Overlap.tsx`（路由 /overlap） | 滞后显眼横幅、穿透表 12 列+权重 bar、>10% 红、持有列悬停贡献明细、未披露末行、一键刷新前 12 只 A 股；组合页顺手补回撤>30%红/相关性>0.8标注（PRD 评分哲学） |
| 测试 | `tests/test_overlap.py` 8 用例（29/29 绿）+ `scripts/verify_m4.py` | 验收 7/7：中际旭创 4.98%/新易盛 4.82% 排前 2、均 3 只共持、未披露 54.7%、滞后 28 天 |

**穿透页正确姿势**：勾基金 → 穿透分析 → 首次个股指标列空 → 点「刷新个股数据」（约 12-25 秒）→ 重跑穿透即全指标。

## M5 交付物地图（2026-10-29）

| 模块 | 文件 | 要点 |
|---|---|---|
| 领域探索 | `routers/explore.py`、`akshare_client.fetch_fund_rank`、`pages/DomainExplore.tsx` | 降级序：快照映射 > 池内标签 > 排行关键词粗筛（20670 只当日缓存）；POST /pool 入研究池自动打标签+单刷；排行收益仅粗筛排序（数据商口径，界面明示） |
| 快照链路 | `ingest/snapshot_import.py`、`routers/snapshot.py`、db 两表（domain_map/snapshot_log） | data/snapshot/YYYY-MM-DD/domain_map.csv → UPSERT + 记账，幂等双保险（重复导入行数恒定）；POST /api/snapshot/import + GET status |
| 任务计划 | `scripts/cron_call.py`、`scripts/setup_m5_tasks.ps1` | FQT_Weekly_Refresh 周一 09:30 全量刷（含基准）；FQT_Daily_Snapshot 每日 10:00；均以 .venv python 调 cron_call.py（urllib 带 token，不踩 curl GBK） |
| 测试 | `tests/test_snapshot_and_explore.py` 5 用例（34/34 绿）+ `scripts/verify_m5.py` | 验收 7/7：医药 60 候选/000960 已在池/入池链路走通/快照幂等 |

**领域页正确姿势**：侧栏「研究 → 领域探索」→ 点领域 chips → 候选表（近1年降序，池内标徽标）→「入研究池」自动单刷约 15-30 秒。快照目录由外部 ZCode 批次产出（或手工放 domain_map.csv），每日 10 点自动导入，也可 POST /api/snapshot/import 手动。

## M6 交付物地图（2026-10-29，阶段 1 收口）

| 模块 | 文件 | 要点 |
|---|---|---|
| 仪表盘 | `routers/dashboard.py`、`pages/Dashboard.tsx`（路由 /dashboard） | 组合加权指标（份额权重/等权标注）+ 主题暴露条（60% 红线超线红标）+ 持仓明细（点行进画像）+ 新鲜度提示 |
| 验收① | `scripts/verify_m6.py` 场景1-5（15/15） | 诊断重演全链路：三件套+超额/穿透排前列/领域探索/仪表盘/新鲜度 |
| 验收② | verify_m6 场景5 附段 | 004195、012920 YTD vs Wind **0.00pp**；000390 差异=口径选择（现金 vs 再投，分红 0.463/基线 24.8% 放大），CSV 净值级验证是数据准确的直接证据 |
| 打磨 | health 加 nav_latest、侧栏显示净值截止、Placeholder 删除 | 六页全实装：仪表盘/画像库/策略/领域探索/组合评估/穿透分析 |

**重要口径备忘（验收②沉淀）**：大额分红年份，§6 现金口径 YTD 会显著高于 Wind/官方 App 的再投口径（000390 2026 实测 +18.6% vs +8.7%）——两者都对，是「分红躺账不追加」与「分红再投」的行为假设差异；给用户讲收益时注意口径，画像页 tooltip 已注明。

**用户数据现状**：池 13 只（持仓 4 + 研究 9，017894 为用户 10-29 经领域页自入）；仅 000390 录了份额（10000 份，ZCode 测试数据**待用户改为真实值**）——仪表盘主题暴露/总市值在录齐份额前按已录份额算。

## 下一步：阶段 2（实盘观察 + 策略演化，无开发里程碑）

- 双周核查自动化（首次 2026-11-11 09:00）：读库生成 brief + Bark 推送 + git push；用户开 ZCode 会话敲 /grill-me 拷问策略。
- 投资侧待办：卖出 011369 资金去向（创新药定投或暂持货币）；用户录真实持仓份额（画像详情页持仓卡）。
- 数据保鲜全自动：周一 09:30 全量刷 + 每日 10:00 快照检测；数据源漂移时跑 scripts/tech_probe_akshare.py 探针。
- Jev 资讯信号层（原阶段 3）待用户决定是否启动（预算 ~$0.02/天）。

## 红线（沿用，不因里程碑变化）

不动 8100/HQ；FQT_Web_Server 任务只 end/run 不改配置；不 bind 公网、不放宽 CORS；akshare 锁 1.19.1；不改 `data/` 已有文件（000390_weekly_nav.csv 是校验基准）；workbench.db、data/shots/、data/cache/ 不入 git；网络外呼只出现在 ingest/；数据缺口界面显式标注不造假；反爬纪律优先于进度。
