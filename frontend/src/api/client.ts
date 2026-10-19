// 后端接口类型与 fetch 封装。所有页面统一从这里走 /api 相对路径。
export interface Fund {
  code: string
  name: string
  pool_type: 'holding' | 'research'
  domain_tags: string[]
  created_at: string
  has_note: boolean
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
}
