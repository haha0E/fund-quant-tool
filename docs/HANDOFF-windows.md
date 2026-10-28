# 会话交接文档（2026-10-28 晚 · M3 完成 → M4 待开工）

> 用途：新会话开工前先读本文 + `ROADMAP.md`（末尾进度行）+ `docs/实现方案-fund-workbench.md`（§1 架构 / §3 库表 / §5 里程碑 / §6 口径）+ `docs/复查报告-重仓基金-20261020.md` §四（口径反转教训）。
> 历史：本文原为 2026-10-14 Windows 迁移交接（uv/GitHub/数据源复测均已完成，详见 ROADMAP 10-14 行），现整体重写为 M2→M3 交接。

## 项目当前状态

- **进度**：M1 ✅ → M2 ✅（2026-10-28）→ **M3 ✅（2026-10-28 晚，含 6 项扩展全部交付，21/21 测试绿 + 生产实测）** → M4 穿透分析页待开工。
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

## 下一步：M4 穿透分析页（~11 月底）

验收原文（§5 不降标准）：**新易盛/中际旭创组合权重排前列、超标标色；报告期滞后标注**。
- 数据已备：fund_holding 存量（000390 2026-09-30 新易盛 7.01%/中际旭创 7.12%）+ 穿透权重口径 Σ(基金权重×占净值比)、前十大外汇总「未披露部分」（§6 已定）。
- 复用：my_position（组合权重）、组合页权重模式、EChart 热力图。
- 个股日频/估值路由（新浪/百度）M2 已注册未用，M4 直接走 source_map.fetch("stock_daily"/"stock_valuation")。

M5 领域探索+快照+任务计划 ~12 月上中、M6 总验收 ~12 月下（重做 10-13 诊断 + 3 基金抽验 ≤0.5pct）。

## 红线（沿用，不因里程碑变化）

不动 8100/HQ；FQT_Web_Server 任务只 end/run 不改配置；不 bind 公网、不放宽 CORS；akshare 锁 1.19.1；不改 `data/` 已有文件（000390_weekly_nav.csv 是校验基准）；workbench.db、data/shots/、data/cache/ 不入 git；网络外呼只出现在 ingest/；数据缺口界面显式标注不造假；反爬纪律优先于进度。
