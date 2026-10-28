# 技术选型文档 · 基金研究工作台（定稿候选 v1.0）

> 阶段：技术选型 → 待用户验收 · 生成于 2026-10-14
> 上游：PRD v0.2（已验收）、前端框架深度对比尽调（另存于 docs/技术选型-前端框架深度对比.md）
> 验证环境：macOS arm64 · Python 3.12 · uv 0.12.18 · akshare 1.19.1（检索/实测于 2026-10-13/14）

## 1. 六项决策总表

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 时序数据源 | akshare 为主（多源冗余，见 §2 实测矩阵），ZCode 落盘保底 |
| 2 | 前端 | FastAPI + React，UI 外壳 Ant Design |
| 3 | 图表 | Apache ECharts（echarts-for-react） |
| 4 | 存储 | SQLite 单库（历史数据 + notes 结论表）+ 结论保存时自动导出 md 快照 |
| 5 | 部署 | Windows 主机独立运行为硬性需求；ZCode 非运行时依赖；验收含「ZCode 离线 7 天功能完整」 |
| 6 | 截面数据管线 | a 档：ZCode 桌面定时自动化（每周一）；c 档：akshare 兜底常驻内置；b 档（无头 CLI）经验证不可行，见 §3 |

新增依赖（相对 PRD）：`curl_cffi`（东财 f10 持仓接口反爬穿透）、`httpx`（FastAPI 生态配套）。

## 2. 实测验证记录——数据可得性矩阵（第一道闸：通过，含代价说明）

每个字段以「最终采用方案 + 实测证据」记录。探测脚本常备于 `scripts/tech_probe_akshare.py` 与 `scripts/tech_probe_akshare2.py`，**Windows 主机上线第一周必须重跑复测**。

| 数据项 | 采用方案 | 实测证据（2026-10-13/14） | 备注 |
|---|---|---|---|
| 基金净值序列（含 QDII） | akshare `fund_open_fund_info_em`（东财 fund 域） | 000390 全史 3117 行；012920 QDII 1110 行；**与库内 Wind 口径 CSV 交叉核对 5/5 个周度点偏差 0.000%** | 验收标准②的预演已通过 |
| 基金档案 | akshare `fund_individual_basic_info_xq`（雪球源） | 000390 返回 14 项档案 | 含经理/成立/规模等 |
| 基金排行与区间收益 | akshare `fund_open_fund_rank_em` | 20547 只，含近1周/1/3/6月/1/2/3年/YTD | 无主题分类列 → 领域筛选依赖映射表+关键字，符合预期 |
| 前十大持仓 | **curl_cffi(impersonate=chrome) 直连东财 fundf10 API** | 000390 返回「2026年2季度股票投资明细」HTML，可解析 | python requests 被 TLS 指纹反爬拦截，curl_cffi 通过 |
| 个股日线（前复权） | akshare `stock_zh_a_hist_tx`（腾讯源） | 新易盛 300502 数据返回，与东财 K 线 JSON 交叉一致 | 东财 push2his 有 IP 频控（本次验证中该域对我们 IP 临时拉黑），**弃用东财行情域** |
| 个股 PE/PB 五年分位 | akshare `stock_zh_valuation_baidu`（百度源） | 300502 近5年 913 行；实测 PE(TTM)=37.4 处 38 分位、PB=20.2 处 77 分位 | 原乐咕个股接口 `stock_a_indicator_lg` 已从 1.19.1 移除——akshare 接口漂移的实证，版本必须锁定 |
| 指数基准 | akshare `stock_zh_index_daily`（新浪源） | 沪深300 全史 6007 行 | 东财指数接口同被频控，弃用 |

### 工程结论（写进实现方案的硬约束）

1. **多源冗余是常态而非备胎**：单一免费源没有全覆盖，最终形态 = akshare（净值/档案/排行/估值/指数/腾讯行情）+ curl_cffi（东财 f10 持仓）两条腿。数据层需按「字段 → 客户端」映射封装，不允许散落在业务代码里。
2. **反爬纪律**：所有外呼带 请求间 sleep + 失败指数退避 + 当日磁盘缓存（PRD 的「行情即时」语义 = 当日缓存命中即算即时）；单源连续失败自动降级到备用源或 ZCode 落盘数据，界面标注数据源与截止时间。
3. **版本锁定**：`akshare==1.19.1` 锁死在 uv.lock；升级 = 手动 + 重跑 probe 脚本全绿后才允许。
4. **残留风险**：① 本次验证在 macOS 完成，Windows 主机网络环境不同，上线首周复测；② 乐咕接口移除事件证明免费接口会漂移，probe 脚本作为常备体检工具保留。

## 3. zcode CLI 无头模式验证（b 档：不可行）

- PATH、npm 全局、`/Applications/ZCode.app`、`~/.zcode/` 全查：**不存在无头 CLI 可执行文件**；App 主二进制启动的是 Electron 桌面进程；`~/.zcode/cli/` 是桌面端的 MCP/插件配置目录。
- 结论：截面管线维持 a（桌面定时自动化，现成能力，每周一随周报批次跑「刷新截面数据」任务）+ c（akshare 兜底：持仓用 curl_cffi/f10，排行+关键字做领域降级）。若官方未来发布无头 CLI，再评估升档。
- 跨机器数据流（Mac 产数据、Windows 消费）：自动化产出**便携快照文件（CSV/JSON）放入同步盘目录**，Windows 端应用启动/定时检测并导入 SQLite；该数据流图在实现方案阶段绘制。

## 4. Windows 主机部署要点（实现方案阶段落实）

- 定时任务用系统「任务计划程序」；常驻用 NSSM 注册服务或开机自启 + 浏览器访问 localhost。
- 代码全链路显式 UTF-8（Windows 控制台默认 GBK，akshare 中文列名必踩）。
- uv 环境 + SQLite 在 Windows 原生支持，无兼容障碍；上线首周跑 probe 复测（§2）。

## 5. 同类项目调研（2026-10-14，用户点名 vibe-trading 触发）

### 5.1 HKUDS/Vibe-Trading（用户点名项目，已深挖架构）

港大开源的「个人金融研究 Agent」，2026 年爆火（GitHub 6k-22k+ stars 区间）。架构：ReAct 循环 + 60-74 个领域工具注册表 + 两级持久化记忆 + 多 Agent 编排；**FastAPI 后端 + React/TypeScript/Vite 前端** + Electron 桌面端 + CLI + MCP Server 多入口；28 个市场数据源自动降级、15+ 券商连接器、10 个回测引擎、462 个预置 Alpha、影子账户（交易日志→规则→回测闭环）、沙盒回测（AST 级危险调用剥离）、90 项金融技能文档。

**对本项目的四点价值：**
1. **技术栈背书**：其 FastAPI+React/TS 选择与我们的选型一致，§1 决策获得同类头部项目实证支持，六项决策不变。
2. **数据层设计借鉴**：其「28 源 Auto-Fallback」印证我们「字段→客户端映射 + 自动降级」的双客户端方案，实现时学它的数据源路由抽象。
3. **影子账户 = 我们阶段 4 的成熟参照**：其「建议→记录→规则化→回测后验」闭环几乎就是 ROADMAP 阶段 4「模拟盘」设想的工程化版本，届时取经。
4. **定位清晰不重叠**：它是交易员/研究员 Agent（策略生成+回测+券商执行，股票/期货/加密多市场），我们是**场外基金研究工作台**（持仓穿透+研究池+结论层+周频调仓辅助）。它不解决基金穿透与隐性集中度，我们有永久非目标「不自动交易」——不是竞品，是可取经的邻居；其 A 股技能（如 ashare-pre-st-filter）证明 A 股数据生态可行。

### 5.2 其他三类项目（结论式记录）

| 类别 | 代表 | 与我们的差异 | 取舍 |
|---|---|---|---|
| 自托管组合追踪 | Ghostfolio（NestJS）、Wealthfolio（本地桌面）、Portfolio Performance（Java 桌面）、LibreFolio | 记账+净值追踪导向，无研究层/穿透/结论层；标的美股为主 | 不引入；数据模型（账户→持仓→交易）可参考 |
| 中文选基工具 | investool（4433 法则自动选基）+ akshare 官方生态 | 策略固定、单品导向，无组合穿透 | 验证品类存在；4433 等选基思路可作领域探索页的候选策略参考 |
| AI 交易 Agent 框架 | TradingAgents（Tauric，20k+ stars，多空辩论+风控 Agent）、awesome-trading-agents 清单 | 面向交易决策，非基金研究 | 阶段 3 信号层演进时回来取经（多空辩论模式替代/增强 Jev 单信号） |

### 5.4 第二轮补充调研（2026-10-14，四条赛道）

| 项目 | 定位 | 与我们的关系 | 取舍结论 |
|---|---|---|---|
| **OpenBB** | 最大开源投研平台（Python 平台 + Workspace UI + Copilot AI 分析师，机构级） | 理念同向（数据源抽象 + AI 协作工作台）但体量与美股导向不适配 | 不引入；其「多数据源统一抽象 + agent 可用的工作台」作为远期形态参照 |
| **virattt/ai-hedge-fund** | 数万星教育向 PoC：多 persona Agent（巴菲特/芒格风格）各出 thesis+signal+置信度，PM/风控层聚合，纯模拟 | 「多信号→置信度→聚合」结构与阶段 3 Jev 信号设计同构，且比 TradingAgents 轻 | 阶段 3 信号层的首选参照（多空辩论 + persona 信号聚合两种模式都记入） |
| **zvt** | 一体化量化数据框架：内置东财免费源，开箱覆盖 A股/指数/**基金净值+十大持仓+财报**，schema 化 SQL 存储，声明式因子计算 | **与我们计划自建的数据层高度重叠**——最接近"现成轮子"的候选 | ~~实现方案阶段安排半天 spike 验证~~ → **已验证，不可用，见下方 spike 结论** |

> **zvt spike 结论（2026-10-14 Windows 实测）：不可用，数据层维持 akshare+curl_cffi 自建。**
> - 版本：PyPI 最新 0.13.1（项目此后无新发布）。**连 import 都不开箱**：需 Python ≤3.11（本项目锁 3.12）+ `numpy<2`（其 pandas 2.0.3 与 numpy 2.x 二进制冲突）+ `setuptools<81`（新版已移除 `pkg_resources`），三处补丁后才能启动。
> - 核心否定：遍历其全部 recorder（`eastmoney.*`：common/dividend_financing/finance/holder/meta/trading；`em.*`：actor/macro/meta/misc/quotes/trading）——**不存在基金净值 recorder**；全包源码检索 `FundNav` 零引用。
> - 十大持仓：`FundStock` schema 存在，但唯一数据生产者是 joinquant 源（`jq_fund_meta_recorder.py`，需付费 JQData 账号），东财免费源不覆盖。README 宣称的"基金净值+十大持仓开箱覆盖"与 0.13.1 实际不符。
> - 连带判断：其 schema 设计参考价值也有限——基金相关 schema 在该版本中没有可用的免费数据生产者，照搬会继承空壳。
| vn.py / qlib | 交易系统开发框架 / 微软 AI 量化研究平台 | vn.py 面向实盘交易（永久非目标）；qlib 数据准备繁琐、基金不内置、ML 因子导向 | 都不用；qlib 留给阶段 3 若做 ML 因子再评 |
| PyPortfolioOpt / Riskfolio-Lib / skfolio | 组合优化库（MVO/BL/HRP；CVaR 全家桶；sklearn 风格） | 对应组合评估页的远期增强；v1 明确无评分无优化（PRD 非目标） | 不入 v1；阶段 4+ 做组合优化时三选一（初判 skfolio 最现代） |

### 5.5 调研对选型的净影响（两轮合并）

六项决策零变更；新增实现方案阶段的「借鉴与验证清单」：
1. 数据源路由与自动降级抽象（Vibe-Trading，28 源 Auto-Fallback）；
2. 影子账户式建议-后验闭环（Vibe-Trading，阶段 4 设计参照）；
3. 多 persona 信号聚合 + 多空辩论（ai-hedge-fund / TradingAgents，阶段 3 演进方向）；
4. ~~**zvt spike（半天）**：数据层自建 vs 采用 zvt 的对照验证~~ → **已完成（2026-10-14）：zvt 不可用，数据层定为 akshare+curl_cffi 自建**（证据见 §5.4 spike 结论）。

## 6. 验收清单（本阶段关闭条件）

1. 用户确认六项决策总表（§1）——尤其数据源双客户端方案与 b 档降级结论；
2. 用户确认实测证据与残留风险（§2）——尤其 Windows 复测条款；
3. 确认后进入实现方案设计阶段（模块划分、数据流图、里程碑与工作量估算）。
