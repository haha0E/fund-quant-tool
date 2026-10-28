// 后端接口类型与 fetch 封装。所有页面统一从这里走 /api 相对路径。
export interface Fund {
  code: string
  name: string
  pool_type: 'holding' | 'research'
  domain_tags: string[]
  created_at: string
  has_note: boolean
}

// ---- M2：单基金画像详情 ----

export interface FundProfile {
  as_of: string
  name: string | null
  full_name: string | null
  fund_type: string | null
  inception_date: string | null
  scale: string | null
  company: string | null
  manager: string | null
  custodian: string | null
  rating: string | null
  benchmark: string | null
  objective: string | null
  strategy: string | null
  fee_management: number | null
  fee_custody: number | null
  fee_subscription: number | null
  fee_redemption: number | null
  stock_position: number | null
  stock_position_as_of: string | null
  tracked_index: string | null
  source: string | null
}

export interface FundMetric {
  as_of: string | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_ytd: number | null
  ret_1y: number | null
  ann_ret: number | null
  max_dd: number | null
  ann_vol: number | null
  sharpe: number | null
}

export interface NavPoint {
  date: string
  unit_nav: number
  acc_nav: number | null
  dividend: number
}

export interface DividendEvent {
  date: string
  dividend: number
}

export interface Holding {
  report_date: string
  stock_code: string
  stock_name: string
  weight: number
}

export interface FundDetail {
  code: string
  name: string
  pool_type: 'holding' | 'research'
  domain_tags: string[]
  profile: FundProfile | null
  metric: FundMetric | null
  nav: NavPoint[]
  dividends: DividendEvent[]
  holdings: Holding[]
  holding_periods: string[]
  note: string
  note_updated_at: string | null
  data_gaps: string[]
}

export interface RefreshSummary {
  scope: string
  seeded: { inserted: string[]; patched: string[] } | null
  funds: Record<string, Record<string, unknown>>
  errors: Record<string, string>
}

// ---- M3：持仓 / 预检 / 草稿 / 策略 / 组合评估 ----

export interface Position {
  code: string
  shares: number
  market_value: number | null
  value_as_of: string | null
  updated_at: string
}

export interface Preflight {
  code: string
  name: string
  fund_type: string | null
  company: string | null
  manager: string | null
  scale: string | null
  inception_date: string | null
  latest_nav_date: string | null
  ret_1y: number | null
  ret_ytd: number | null
  integrity_bad: boolean
  warnings: string[]
}

export interface StrategyFile {
  filename: string
  title: string
  updated_at: string
}

export interface StrategyContent extends StrategyFile {
  content: string
}

export interface PortfolioResult {
  codes: string[]
  weights_used: Record<string, number>
  weight_mode: string
  benchmark: string | null
  benchmark_name: string | null
  portfolio_metric: FundMetric | null
  members: { code: string; name: string; weight: number; metric: FundMetric | null }[]
  nav_dates: string[]
  portfolio_nav: number[]
  benchmark_nav: number[]
  excess: Record<string, number | null>
  corr_codes: string[]
  corr_matrix: (number | null)[][]
  data_gaps: string[]
}

// FundDetail 的 position 字段（M3）
export interface FundDetailWithPosition extends FundDetail {
  position: Position | null
}

/* ---- 写接口 token（M3）：localStorage 存一次，401 时全局弹窗补录 ---- */

const TOKEN_KEY = 'fqt-token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token.trim())
}

export const AUTH_REQUIRED_EVENT = 'fqt:auth-required'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? 'GET'
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (method !== 'GET' && method !== 'HEAD') {
    const t = getToken()
    if (t) headers['X-FQT-Token'] = t
  }
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT))
    throw new Error('写接口需要鉴权（token）——请在弹窗里粘贴一次')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `请求失败 (${res.status})`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  listFunds: (pool?: string) =>
    request<Fund[]>(`/api/funds${pool ? `?pool=${pool}` : ''}`),
  addFund: (fund: { code: string; name: string; pool_type: 'holding' | 'research'; domain_tags: string[] }) =>
    request<Fund>('/api/funds', { method: 'POST', body: JSON.stringify(fund) }),
  removeFund: (code: string) =>
    request<void>(`/api/funds/${code}`, { method: 'DELETE' }),
  // M2：详情 + 结论 + 刷新
  getFundDetail: (code: string) =>
    request<FundDetailWithPosition>(`/api/funds/${code}`),
  getNote: (code: string) =>
    request<{ fund_code: string; content: string; updated_at: string }>(`/api/funds/${code}/note`),
  saveNote: (code: string, content: string) =>
    request<{ fund_code: string; content: string; updated_at: string }>(
      `/api/funds/${code}/note`, { method: 'PUT', body: JSON.stringify({ content }) }),
  refresh: (scope: 'nav' | 'profile' | 'holdings' | 'metrics' | 'index' | 'all', code?: string) =>
    request<RefreshSummary>(`/api/refresh?scope=${scope}${code ? `&code=${code}` : ''}`, { method: 'POST' }),
  // M3：持仓 / 预检 / 草稿 / 策略 / 组合 / 鉴权
  savePosition: (code: string, shares: number) =>
    request<Position>(`/api/funds/${code}/position`, { method: 'PUT', body: JSON.stringify({ shares }) }),
  clearPosition: (code: string) =>
    request<void>(`/api/funds/${code}/position`, { method: 'DELETE' }),
  preflight: (code: string) =>
    request<Preflight>(`/api/funds/preflight/${code}`),
  noteDraft: (code: string) =>
    request<{ draft: string }>(`/api/funds/${code}/note/draft`),
  listStrategy: () =>
    request<StrategyFile[]>('/api/strategy'),
  getStrategy: (filename: string) =>
    request<StrategyContent>(`/api/strategy/${encodeURIComponent(filename)}`),
  evalPortfolio: (body: { codes: string[]; weights?: Record<string, number>; benchmark?: string | null }) =>
    request<PortfolioResult>('/api/portfolio/eval', { method: 'POST', body: JSON.stringify(body) }),
  authStatus: () =>
    request<{ enabled: boolean; hint: string }>('/api/auth/status'),
}

// 指标口径 tooltip（与 backend/app/services/metrics.py TOOLTIPS 同义，§6 强制）
export const METRIC_TOOLTIPS = {
  ret: '区间收益率：窗内无分红=单位净值比值；窗内有分红=(期末单位净值+窗内分红现金)/期初单位净值。禁止用累计净值（历史分红常数会阻尼失真）。',
  ann_ret: '年化收益：自算 (1+区间收益)^(365/天数)-1，不采用数据商年化列。口径为近1年窗口。',
  max_dd: '最大回撤（近1年）：单位净值 running max 取最深跌幅；窗内含分红日先按「单位+窗内累计分红」重构。',
  ann_vol: '年化波动率：日收益标准差×√252（近1年）；分红日按含现金口径计日收益；QDII 用可得交易日。',
  sharpe: '夏普：(年化收益-无风险2%)/年化波动。无风险利率固定 2%。',
} as const
