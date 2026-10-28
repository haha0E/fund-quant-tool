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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
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
    request<FundDetail>(`/api/funds/${code}`),
  getNote: (code: string) =>
    request<{ fund_code: string; content: string; updated_at: string }>(`/api/funds/${code}/note`),
  saveNote: (code: string, content: string) =>
    request<{ fund_code: string; content: string; updated_at: string }>(
      `/api/funds/${code}/note`, { method: 'PUT', body: JSON.stringify({ content }) }),
  refresh: (scope: 'nav' | 'profile' | 'holdings' | 'metrics' | 'all', code?: string) =>
    request<RefreshSummary>(`/api/refresh?scope=${scope}${code ? `&code=${code}` : ''}`, { method: 'POST' }),
}

// 指标口径 tooltip（与 backend/app/services/metrics.py TOOLTIPS 同义，§6 强制）
export const METRIC_TOOLTIPS = {
  ret: '区间收益率：窗内无分红=单位净值比值；窗内有分红=(期末单位净值+窗内分红现金)/期初单位净值。禁止用累计净值（历史分红常数会阻尼失真）。',
  ann_ret: '年化收益：自算 (1+区间收益)^(365/天数)-1，不采用数据商年化列。口径为近1年窗口。',
  max_dd: '最大回撤（近1年）：单位净值 running max 取最深跌幅；窗内含分红日先按「单位+窗内累计分红」重构。',
  ann_vol: '年化波动率：日收益标准差×√252（近1年）；分红日按含现金口径计日收益；QDII 用可得交易日。',
  sharpe: '夏普：(年化收益-无风险2%)/年化波动。无风险利率固定 2%。',
} as const
