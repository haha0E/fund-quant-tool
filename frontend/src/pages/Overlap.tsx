import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { DownloadCloud, Search, Share2 } from 'lucide-react'
import { api, type Fund, type OverlapResult } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// 穿透分析页（M4，PRD FR2③/FR3）：同名重仓股合并、组合级穿透权重、
// 未披露部分条目、报告期滞后显眼标注；单股穿透权重 >10% 红（PRD 评分哲学）。
// 个股指标来自新浪前复权日频 + 百度估值（PE/PB + 序列分位），未摄取时「刷新个股数据」。

type WeightMode = 'auto' | 'equal' | 'manual'
const STOCK_FETCH_LIMIT = 12  // 「刷新个股数据」拉穿透表前 N 只 A 股

function pct(v: number | null | undefined, digits = 1): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

function toneClass(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'text-foreground'
  return v > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
}

export default function Overlap() {
  const [funds, setFunds] = useState<Fund[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [mode, setMode] = useState<WeightMode>('auto')
  const [manual, setManual] = useState<Record<string, string>>({})
  const [result, setResult] = useState<OverlapResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [fetchingStocks, setFetchingStocks] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.listFunds()
        setFunds(list)
        setSelected(new Set(list.filter(f => f.pool_type === 'holding').map(f => f.code)))
      } catch (e) {
        toast.error((e as Error).message)
      }
    })()
  }, [])

  const holdings = funds.filter(f => f.pool_type === 'holding')
  const research = funds.filter(f => f.pool_type === 'research')

  const toggle = (code: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  const analyze = async () => {
    if (selected.size === 0) {
      toast.warning('先勾选至少一只基金')
      return
    }
    setLoading(true)
    try {
      const codes = [...selected]
      const weights = mode === 'manual'
        ? codes.map(c => parseFloat(manual[c] ?? '') || 1)
        : undefined
      setResult(await api.getOverlap(codes, weights))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const refreshStocks = async () => {
    const aShares = result?.stocks.filter(s => s.a_share).slice(0, STOCK_FETCH_LIMIT)
      .map(s => s.stock_code) ?? []
    if (aShares.length === 0) {
      toast.info('没有可刷新的 A 股（先跑一次穿透）')
      return
    }
    setFetchingStocks(true)
    toast.info(`正在拉 ${aShares.length} 只个股行情/估值（反爬限速，约 ${aShares.length * 2} 秒）…`)
    try {
      const r = await api.refreshStocks(aShares)
      const errs = Object.entries((r as unknown as { errors: Record<string, string> }).errors ?? {})
      if (errs.length > 0) {
        toast.warning(`部分失败：${errs.map(([k, v]) => `${k}: ${v}`).join('；').slice(0, 120)}`)
      } else {
        toast.success('个股数据已更新')
      }
      await analyze()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setFetchingStocks(false)
    }
  }

  const renderFundRow = (f: Fund) => {
    const on = selected.has(f.code)
    return (
      <div key={f.code} className="flex items-center gap-2 border-b border-dashed py-1.5 last:border-b-0">
        <button
          type="button"
          onClick={() => toggle(f.code)}
          aria-pressed={on}
          className={cn(
            'size-4 shrink-0 rounded border transition-colors',
            on ? 'border-primary bg-primary text-primary-foreground' : 'border-border',
          )}
        >
          {on && <span className="block text-[10px] leading-4">✓</span>}
        </button>
        <span className="min-w-0 flex-1 truncate text-[13px]">
          {f.name || f.code}
          <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">{f.code}</span>
        </span>
        {mode === 'manual' && on && (
          <input
            value={manual[f.code] ?? ''}
            onChange={e => setManual(prev => ({ ...prev, [f.code]: e.target.value }))}
            inputMode="decimal"
            placeholder="1"
            aria-label={`${f.name} 权重`}
            className="h-7 w-16 rounded-md border bg-transparent px-2 text-right text-xs tabular-nums outline-none focus:border-primary"
          />
        )}
      </div>
    )
  }

  const overLimit = result?.over_limit ?? 0.10
  const rows = useMemo(() => {
    if (!result) return []
    const stockRows = result.stocks
    const undisclosedRow = result.undisclosed > 0.0005
      ? [{ stock_code: '__undisclosed__', stock_name: '未披露部分（前十大之外合计）',
          weight: result.undisclosed, fund_count: 0, funds: [], a_share: true,
          as_of: null, ret_3m: null, ret_6m: null, ret_ytd: null, pos_52w: null,
          ann_vol: null, max_dd_1y: null, pe_ttm: null, pb: null, pe_pct: null, pb_pct: null,
          undisclosed: true }]
      : []
    return [...stockRows, ...undisclosedRow]
  }, [result])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">穿透分析</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            重仓股合并穿透：组合级个股合计权重与量化指标（口径：Σ 基金权重×占净值比）
          </p>
        </div>
        <div className="flex items-center gap-2">
          {result && (
            <Button variant="outline" onClick={() => void refreshStocks()} disabled={fetchingStocks}>
              <DownloadCloud className="size-4" />{fetchingStocks ? '拉取中…' : '刷新个股数据'}
            </Button>
          )}
          <Button onClick={() => void analyze()} disabled={loading || selected.size === 0}>
            <Search className="size-4" />{loading ? '穿透中…' : '穿透分析'}
          </Button>
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-4">
        {/* 左：成员与权重 */}
        <Card className="flex flex-col gap-3 p-4 lg:col-span-1">
          <div className="grid gap-1.5">
            <Label>权重模式</Label>
            <div className="flex gap-1">
              {([['auto', '持仓份额'], ['equal', '等权'], ['manual', '手调']] as const).map(([v, label]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setMode(v)}
                  aria-pressed={mode === v}
                  className={cn(
                    'h-7 flex-1 rounded-md border text-xs transition-colors',
                    mode === v ? 'border-primary bg-primary text-primary-foreground' : 'border-border text-muted-foreground hover:bg-muted',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {mode === 'auto' && '份额×最新净值占比（未录份额回退等权）'}
              {mode === 'equal' && '各基金等权（1/N）'}
              {mode === 'manual' && '输入任意正数，内部归一'}
            </p>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">持仓（{holdings.length}）</div>
            {holdings.map(renderFundRow)}
            <div className="mb-1 mt-3 text-xs font-medium text-muted-foreground">研究池（{research.length}）</div>
            {research.map(renderFundRow)}
          </div>
        </Card>

        {/* 右：结果 */}
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-3">
          {!result ? (
            <Card className="grid place-items-center py-20 text-center text-sm text-muted-foreground">
              <div className="flex flex-col items-center gap-2">
                <Share2 className="size-5 opacity-50" aria-hidden />
                左侧勾选基金，点「穿透分析」看组合实际押注了什么
              </div>
            </Card>
          ) : (
            <>
              {/* 报告期滞后：显眼标注（FR3 口径诚实） */}
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                <span className="font-medium">穿透基于最新披露报告期，数据天然滞后：</span>
                {result.members.map(m => (
                  <Badge key={m.code} variant="outline" className="border-amber-500/50 text-[11px] tabular-nums">
                    {m.name || m.code} @{m.report_date}（滞后 {m.lag_days} 天）
                  </Badge>
                ))}
              </div>

              {result.data_gaps.length > 0 && (
                <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                  <span className="font-medium">数据缺口：</span>{result.data_gaps.join('；')}
                </div>
              )}

              {/* 摘要卡 */}
              <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
                <Card className="gap-0 p-3.5">
                  <div className="text-xs text-muted-foreground">有效持仓数</div>
                  <div className="mt-1 text-[20px] font-semibold tabular-nums">
                    {result.effective_count}
                    <span className="ml-1 text-xs font-normal text-muted-foreground">只（权重≥{(result.effective_min_weight * 100).toFixed(0)}%）</span>
                  </div>
                </Card>
                <Card className="gap-0 p-3.5">
                  <div className="text-xs text-muted-foreground">未披露部分</div>
                  <div className="mt-1 text-[20px] font-semibold tabular-nums">
                    {(result.undisclosed * 100).toFixed(1)}%
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">前十大之外合计，穿透精度上限</div>
                </Card>
                <Card className="gap-0 p-3.5">
                  <div className="text-xs text-muted-foreground">穿透个股</div>
                  <div className="mt-1 text-[20px] font-semibold tabular-nums">{result.stocks.length} 只</div>
                </Card>
                <Card className="gap-0 p-3.5">
                  <div className="text-xs text-muted-foreground">超标线（单股）</div>
                  <div className="mt-1 text-[20px] font-semibold tabular-nums text-red-600 dark:text-red-400">
                    {'>'}{(overLimit * 100).toFixed(0)}%<span className="ml-1 text-xs font-normal text-muted-foreground">红色标注</span>
                  </div>
                </Card>
              </div>

              {/* 成员行 */}
              <Card className="gap-1.5 p-3.5">
                <div className="text-xs font-medium text-muted-foreground">成员权重与前十大覆盖</div>
                <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
                  {result.members.map(m => (
                    <span key={m.code} className="tabular-nums">
                      {(m.name || m.code)}：<span className="font-medium">{(m.weight * 100).toFixed(1)}%</span>
                      <span className="ml-1 text-[11px] text-muted-foreground">（前十覆盖 {(m.top10_sum * 100).toFixed(0)}%）</span>
                    </span>
                  ))}
                </div>
              </Card>

              {/* 穿透表 */}
              <Card className="gap-2 p-4">
                <div className="text-sm font-medium">组合穿透表（按穿透权重降序）</div>
                <div className="overflow-x-auto">
                  <Table className="text-[13px]">
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        {['股票', '穿透权重', '持有', '近3月', 'YTD', '52周位', '波动(1y)', '回撤(1y)', 'PE', 'PE分位', 'PB', 'PB分位'].map(h => (
                          <TableHead key={h} className="h-8 whitespace-nowrap px-2 text-right text-xs">{h}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map(s => {
                        const over = !('undisclosed' in s) && s.weight > overLimit
                        const isUnd = 'undisclosed' in s
                        return (
                          <TableRow key={s.stock_code} className={cn(isUnd && 'bg-muted/40', over && 'bg-red-500/10')}>
                            <TableCell className="whitespace-nowrap px-2 py-1.5">
                              <span className="font-medium">{s.stock_name ?? s.stock_code}</span>
                              <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">{s.stock_code}</span>
                              {!isUnd && !s.a_share && (
                                <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">港/美</Badge>
                              )}
                            </TableCell>
                            <TableCell className={cn('px-2 py-1.5 text-right font-semibold tabular-nums', over && 'text-red-600 dark:text-red-400')}>
                              {(s.weight * 100).toFixed(2)}%
                              {!isUnd && (
                                <span className="ml-1.5 inline-block h-1.5 rounded-sm bg-primary/60 align-middle" style={{ width: `${Math.min(s.weight * 1000, 70)}px` }} aria-hidden />
                              )}
                            </TableCell>
                            {!isUnd ? (
                              <TableCell className="px-2 py-1.5 text-right tabular-nums">
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span className="cursor-help underline decoration-dotted underline-offset-2">{s.fund_count} 只</span>
                                  </TooltipTrigger>
                                  <TooltipContent side="top" className="max-w-64 text-xs">
                                    {s.funds.map(f => (
                                      <div key={f.code} className="tabular-nums">
                                        {f.code}：占净值 {f.weight_pct.toFixed(2)}% → 穿透贡献 {(f.contrib * 100).toFixed(2)}%
                                      </div>
                                    ))}
                                  </TooltipContent>
                                </Tooltip>
                              </TableCell>
                            ) : <TableCell className="px-2 py-1.5 text-right text-muted-foreground">—</TableCell>}
                            <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(s.ret_3m))}>{pct(s.ret_3m)}</TableCell>
                            <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(s.ret_ytd))}>{pct(s.ret_ytd)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums">{s.pos_52w == null ? '—' : s.pos_52w.toFixed(2)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums">{pct(s.ann_vol)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums text-green-600 dark:text-green-400">{pct(s.max_dd_1y)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums">{s.pe_ttm == null ? '—' : s.pe_ttm.toFixed(1)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums">{s.pe_pct == null ? '—' : s.pe_pct.toFixed(2)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums">{s.pb == null ? '—' : s.pb.toFixed(1)}</TableCell>
                            <TableCell className="px-2 py-1.5 text-right tabular-nums">{s.pb_pct == null ? '—' : s.pb_pct.toFixed(2)}</TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  穿透权重 = Σ(基金权重 × 个股占净值比)，前十大截面合并；{'>'}{(overLimit * 100).toFixed(0)}% 红。
                  行情为新浪前复权、估值为百度源（PE/PB 及其序列分位，样本 2020 至今约 5 年）；
                  港股/美股无路由标「港/美」。持有列悬停看各基金贡献明细。
                </p>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
