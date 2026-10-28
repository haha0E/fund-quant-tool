import { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { toast } from 'sonner'
import { Calculator, CircleHelp, Info } from 'lucide-react'
import { api, METRIC_TOOLTIPS, type Fund, type PortfolioResult } from '@/api/client'
import { EChart } from '@/components/EChart'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// 组合评估页（M3 验收主体）：等权/手调权重可切换 + 相关性热力图 + 基准超额。
// 口径与后端 services/portfolio.py 同义：共同交易日对齐、日收益现金分红口径、
// 权重每日再平衡、基准为价格指数（未含股息）。

type WeightMode = 'auto' | 'equal' | 'manual'
type Benchmark = 'sh000300' | 'sh000852' | 'none'

const BENCH_LABELS: Record<Benchmark, string> = {
  sh000300: '沪深300', sh000852: '中证1000', none: '不对比基准',
}

function pct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

function num(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(2)
}

function toneClass(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'text-foreground'
  return v > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
}

/* ---------- 图 option ---------- */

function navChartOption(r: PortfolioResult, bench: Benchmark): Record<string, unknown> {
  const dates = r.nav_dates
  const port = r.portfolio_nav
  const hasBench = bench !== 'none' && r.benchmark_nav.length === port.length
  let peak = -Infinity
  const dd = port.map(v => { peak = Math.max(peak, v); return +(v / peak - 1).toFixed(6) })
  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', confine: true },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    legend: { top: 0, textStyle: { fontSize: 11, color: '#888' } },
    grid: [
      { left: 48, right: 16, top: 28, height: '52%' },
      { left: 48, right: 16, top: '76%', height: '20%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisTick: { show: false } },
      {
        type: 'category', data: dates, gridIndex: 1,
        axisLine: { lineStyle: { color: '#8888' } },
        axisLabel: { color: '#888', fontSize: 10, formatter: (v: string) => v.slice(2, 7) },
      },
    ],
    yAxis: [
      {
        type: 'value', gridIndex: 0, scale: true,
        axisLabel: { color: '#888', fontSize: 10, formatter: (v: number) => v.toFixed(2) },
        splitLine: { lineStyle: { color: '#8883' } },
      },
      {
        type: 'value', gridIndex: 1, max: 0,
        axisLabel: { color: '#888', fontSize: 10, formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '组合（起点=1）', type: 'line', data: port, xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, lineStyle: { width: 1.6, color: '#2563eb' }, itemStyle: { color: '#2563eb' },
      },
      ...(hasBench ? [{
        name: `${BENCH_LABELS[bench]}（起点=1）`, type: 'line', data: r.benchmark_nav,
        xAxisIndex: 0, yAxisIndex: 0, showSymbol: false,
        lineStyle: { width: 1.2, color: '#f59e0b', type: 'dashed' },
        itemStyle: { color: '#f59e0b' },
      }] : []),
      {
        name: '组合回撤', type: 'line', data: dd, xAxisIndex: 1, yAxisIndex: 1,
        showSymbol: false, lineStyle: { width: 1.2, color: '#16a34a' },
        areaStyle: { color: 'rgba(22,163,74,0.18)' }, itemStyle: { color: '#16a34a' },
      },
    ],
  }
}

function corrChartOption(r: PortfolioResult): Record<string, unknown> {
  const names = r.corr_codes
  const data: [number, number, number][] = []
  r.corr_matrix.forEach((row, i) => row.forEach((v, j) => {
    if (v != null) data.push([j, i, +v.toFixed(2)])
  }))
  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: {
      confine: true,
      formatter: (p: { value: [number, number, number] }) =>
        `${names[p.value[0]]} × ${names[p.value[1]]}：${p.value[2].toFixed(2)}`,
    },
    grid: { left: 64, right: 24, top: 12, bottom: 48 },
    xAxis: { type: 'category', data: names, axisLabel: { fontSize: 10, color: '#888' } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 10, color: '#888' } },
    visualMap: {
      min: -1, max: 1, calculable: false, orient: 'horizontal',
      left: 'center', bottom: 0, itemHeight: 90, textStyle: { fontSize: 10, color: '#888' },
      inRange: { color: ['#16a34a', '#f5f5f5', '#dc2626'] },
    },
    series: [{
      type: 'heatmap', data,
      label: { show: true, fontSize: 10, color: '#333',
        formatter: (p: { value: [number, number, number] }) => p.value[2].toFixed(2) },
    }],
  }
}

/* ---------- 页面 ---------- */

export default function Portfolio() {
  const [funds, setFunds] = useState<Fund[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [mode, setMode] = useState<WeightMode>('auto')
  const [manual, setManual] = useState<Record<string, string>>({})
  const [bench, setBench] = useState<Benchmark>('sh000300')
  const [result, setResult] = useState<PortfolioResult | null>(null)
  const [evaluating, setEvaluating] = useState(false)

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

  const manualTotal = useMemo(() =>
    Object.entries(manual)
      .filter(([c]) => selected.has(c))
      .reduce((s, [, v]) => s + (parseFloat(v) || 0), 0), [manual, selected])

  const evaluate = async () => {
    if (selected.size === 0) {
      toast.warning('先勾选至少一只基金')
      return
    }
    setEvaluating(true)
    try {
      const codes = [...selected]
      let body: { codes: string[]; weights?: Record<string, number>; benchmark?: string | null }
      if (mode === 'manual') {
        const weights: Record<string, number> = {}
        for (const c of codes) weights[c] = parseFloat(manual[c] ?? '') || 1
        body = { codes, weights, benchmark: bench === 'none' ? null : bench }
      } else {
        body = { codes, benchmark: bench === 'none' ? null : bench }
      }
      const r = await api.evalPortfolio(body)
      setResult(r)
      if (mode === 'auto' && r.weight_mode === 'equal') {
        toast.info('有成员未录持仓份额，已回退等权（画像详情页可录份额）')
      }
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setEvaluating(false)
    }
  }

  const m = result?.portfolio_metric

  const memberRows = useMemo(() => {
    if (!result) return []
    return [
      {
        code: '__portfolio__', name: '组合', weight: 1, metric: result.portfolio_metric,
        isPortfolio: true,
      },
      ...result.members.map(x => ({ ...x, isPortfolio: false })),
    ]
  }, [result])

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
        {mode !== 'manual' && result?.weights_used[f.code] != null && (
          <span className="w-12 text-right text-xs text-muted-foreground tabular-nums">
            {(result.weights_used[f.code] * 100).toFixed(1)}%
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">组合评估</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            净值合成（共同交易日·日收益现金分红口径·权重每日再平衡）与基准超额
          </p>
        </div>
        <Button onClick={() => void evaluate()} disabled={evaluating || selected.size === 0}>
          <Calculator className="size-4" />{evaluating ? '计算中…' : '评估组合'}
        </Button>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-4">
        {/* 左：成员与参数 */}
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
              {mode === 'auto' && '份额×最新净值占比（未录份额的成员会回退等权）'}
              {mode === 'equal' && '各成员等权（1/N）'}
              {mode === 'manual' && `输入任意正数，内部归一${manualTotal > 0 ? `（当前合计 ${manualTotal.toFixed(2)}）` : ''}`}
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label>基准</Label>
            <Select value={bench} onValueChange={v => setBench(v as Benchmark)}>
              <SelectTrigger className="h-8 w-full text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(BENCH_LABELS).map(([v, label]) => (
                  <SelectItem key={v} value={v} className="text-xs">{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">价格指数（未含股息）；先对齐共同交易日再算超额</p>
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
          {result?.data_gaps && result.data_gaps.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              <span className="font-medium">数据缺口：</span>{result.data_gaps.join('；')}
            </div>
          )}

          {!result ? (
            <Card className="grid place-items-center py-20 text-center text-sm text-muted-foreground">
              <div className="flex flex-col items-center gap-2">
                <Info className="size-5 opacity-50" aria-hidden />
                左侧选成员与权重模式，点「评估组合」出结果
              </div>
            </Card>
          ) : evaluating ? (
            <div className="grid gap-3 sm:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[72px]" />)}</div>
          ) : (
            <>
              {/* 指标卡：组合核心 + 超额 */}
              <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
                {([
                  ['近1年', m?.ret_1y, METRIC_TOOLTIPS.ret, toneClass(m?.ret_1y)],
                  ['今年以来', m?.ret_ytd, METRIC_TOOLTIPS.ret, toneClass(m?.ret_ytd)],
                  // 回撤 >30% 红（PRD 评分哲学），否则绿
                  ['最大回撤(1y)', m?.max_dd, `${METRIC_TOOLTIPS.max_dd}（超 -30% 标红）`,
                    m?.max_dd != null && m.max_dd < -0.30 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'],
                  ['年化波动(1y)', m?.ann_vol, METRIC_TOOLTIPS.ann_vol, ''],
                  ['夏普(1y)', m?.sharpe, METRIC_TOOLTIPS.sharpe, toneClass(m?.sharpe)],
                ] as const).map(([label, value, tooltip, cls]) => (
                  <Card key={label} className="gap-0 p-3.5">
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      {label}
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <CircleHelp className="size-3 cursor-help opacity-60" aria-label={`${label}口径`} />
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-72 text-xs leading-relaxed">{tooltip}</TooltipContent>
                      </Tooltip>
                    </div>
                    <div className={cn('mt-1 text-[20px] font-semibold tabular-nums',
                      typeof value === 'number' ? cls : '')}>
                      {typeof value === 'number' ? pct(value) : num(value)}
                    </div>
                  </Card>
                ))}
              </div>

              {/* 超额（基准存在时） */}
              {result.benchmark && (
                <Card className="gap-2 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium">
                      基准超额 <span className="text-xs font-normal text-muted-foreground">（组合 − {result.benchmark_name}，对齐后同窗相减）</span>
                    </div>
                    <Badge variant="outline" className="text-[11px]">{result.benchmark_name}</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                    {([['近1月', 'ret_1m'], ['近3月', 'ret_3m'], ['近6月', 'ret_6m'], ['今年以来', 'ret_ytd'], ['近1年', 'ret_1y']] as const)
                      .map(([label, key]) => (
                        <div key={key} className="rounded-lg border px-2.5 py-2">
                          <div className="text-[11px] text-muted-foreground">{label}</div>
                          <div className={cn('text-sm font-semibold tabular-nums', toneClass(result.excess[key]))}>
                            {pct(result.excess[key])}
                          </div>
                        </div>
                      ))}
                  </div>
                </Card>
              )}

              {/* 净值/回撤图 */}
              <Card className="gap-2 p-4">
                <div className="text-sm font-medium">组合净值与回撤</div>
                <EChart option={navChartOption(result, bench)} height={320} />
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  组合净值从 1 起步，按共同交易日日收益累乘（权重每日再平衡）；回撤为该序列 running max 最深跌幅。
                  {result.benchmark && ' 基准同窗对齐后归一到 1 对比（价格指数，未含股息）。'}
                </p>
              </Card>

              {/* 成员并排指标 */}
              <Card className="gap-2 p-4">
                <div className="text-sm font-medium">组合 vs 成员并排（库内已算指标）</div>
                <div className="overflow-x-auto">
                  <Table className="text-[13px]">
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        {['', '近1月', '近3月', 'YTD', '近1年', '回撤(1y)', '波动(1y)', '夏普(1y)'].map(h => (
                          <TableHead key={h} className="h-8 px-2 text-right text-xs">{h}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {memberRows.map(row => (
                        <TableRow key={row.code} className={cn(row.isPortfolio && 'bg-muted/50 font-medium')}>
                          <TableCell className="px-2 py-1.5">
                            <span className="whitespace-nowrap">{row.name}</span>
                            <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">
                              {row.isPortfolio ? '' : `${row.code}·${(row.weight * 100).toFixed(1)}%`}
                            </span>
                          </TableCell>
                          {([['ret_1m'], ['ret_3m'], ['ret_ytd'], ['ret_1y']] as const).map(([k]) => (
                            <TableCell key={k} className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(row.metric?.[k]))}>
                              {pct(row.metric?.[k])}
                            </TableCell>
                          ))}
                          <TableCell className="px-2 py-1.5 text-right tabular-nums text-green-600 dark:text-green-400">
                            {pct(row.metric?.max_dd)}
                          </TableCell>
                          <TableCell className="px-2 py-1.5 text-right tabular-nums">{pct(row.metric?.ann_vol)}</TableCell>
                          <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(row.metric?.sharpe))}>
                            {num(row.metric?.sharpe)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </Card>

              {/* 相关性热力图 */}
              <Card className="gap-2 p-4">
                <div className="text-sm font-medium">成员日收益相关性（两两共同交易日，pearson）</div>
                {result.corr_codes.length >= 2 ? (
                  <EChart option={corrChartOption(result)} height={Math.max(200, result.corr_codes.length * 52 + 60)} />
                ) : (
                  <div className="grid h-20 place-items-center text-sm text-muted-foreground">单成员无相关性可算</div>
                )}
                <p className="text-[11px] text-muted-foreground">
                  颜色越红相关性越高；|相关|{'>'}0.8 视为高同涨同跌（PRD 标黄线），减仓讨论时优先关注。
                </p>
              </Card>

              {result.nav_dates.length > 0 && (
                <p className="text-[11px] text-muted-foreground">
                  序列 {dayjs(result.nav_dates[0]).format('YYYY-MM-DD')} → {dayjs(result.nav_dates[result.nav_dates.length - 1]).format('YYYY-MM-DD')}
                  （{result.nav_dates.length} 个共同交易日）；权重模式 {result.weight_mode === 'position' ? '份额×净值' : result.weight_mode === 'equal' ? '等权' : '手调'}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
