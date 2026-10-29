import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { toast } from 'sonner'
import { AlertTriangle, LayoutDashboard } from 'lucide-react'
import { api, METRIC_TOOLTIPS, type DashboardData } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { CircleHelp } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// 仪表盘（M6，PRD FR4 首页）：持仓总览——收益/风险一眼看 + 主题暴露 + 数据新鲜度。

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

function toneClass(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'text-foreground'
  return v > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
}

function MetricCard({ label, value, tooltip, className }: {
  label: string; value: string; tooltip: string; className?: string
}) {
  return (
    <Card className="gap-0 p-3.5">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        {label}
        <Tooltip>
          <TooltipTrigger asChild>
            <CircleHelp className="size-3 cursor-help opacity-60" aria-label={`${label}口径`} />
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-72 text-xs leading-relaxed">{tooltip}</TooltipContent>
        </Tooltip>
      </div>
      <div className={cn('mt-1 text-[20px] font-semibold tabular-nums', className)}>{value}</div>
    </Card>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)

  const reload = useCallback(async () => {
    try {
      setData(await api.getDashboard())
    } catch (e) {
      toast.error((e as Error).message)
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  if (!data) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-56" />
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[72px]" />)}</div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  const m = data.portfolio_metric
  const overThemes = data.theme_exposure.filter(t => t.pct != null && t.pct > data.theme_limit)
  const navStale = data.holdings.filter(h => h.nav_as_of && dayjs().diff(dayjs(h.nav_as_of), 'day') > 4)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">仪表盘</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            持仓总览（{data.as_of}）· 组合指标按
            {data.weight_mode === 'position' ? '份额×净值' : '等权'}加权（每日再平衡合成）
          </p>
        </div>
        <Button variant="ghost" size="icon" className="size-9" onClick={() => void reload()} aria-label="刷新">
          <LayoutDashboard className="size-4" />
        </Button>
      </div>

      {/* 组合指标卡 */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="总市值" value={data.total_market_value != null
          ? `${(data.total_market_value / 10000).toLocaleString(undefined, { maximumFractionDigits: 1 })} 万` : '—（未录份额）'}
          tooltip="Σ(份额×最新单位净值)；未录份额的持仓不计入。" />
        <MetricCard label="组合 YTD" value={pct(m?.ret_ytd)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_ytd)} />
        <MetricCard label="组合 近1年" value={pct(m?.ret_1y)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_1y)} />
        <MetricCard label="组合 回撤(1y)" value={pct(m?.max_dd)} tooltip={`${METRIC_TOOLTIPS.max_dd}（超 -30% 标红）`}
          className={m?.max_dd != null && m.max_dd < -0.30 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'} />
        <MetricCard label="组合 夏普(1y)" value={m?.sharpe != null ? m.sharpe.toFixed(2) : '—'} tooltip={METRIC_TOOLTIPS.sharpe} className={toneClass(m?.sharpe)} />
      </div>

      {/* 主题暴露（策略红线检查位） */}
      {data.theme_exposure.length > 0 && (
        <Card className="gap-2 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium">主题暴露（按市值，策略红线：单一主题 ≤{(data.theme_limit * 100).toFixed(0)}%）</div>
            {overThemes.length > 0 && (
              <Badge className="bg-red-500/15 border border-red-500/40 text-[11px] text-red-700 dark:text-red-400">
                <AlertTriangle className="size-3" />超线：{overThemes.map(t => t.theme).join('、')}
              </Badge>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            {data.theme_exposure.map(t => (
              <div key={t.theme} className="flex items-center gap-2 text-[13px]">
                <span className="w-16 shrink-0 text-muted-foreground">{t.theme}</span>
                <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                  <div className={cn('h-full rounded-full',
                    t.pct != null && t.pct > data.theme_limit ? 'bg-red-500' : 'bg-primary')}
                    style={{ width: `${Math.min((t.pct ?? 0) * 100, 100)}%` }} aria-hidden />
                </div>
                <span className="w-24 shrink-0 text-right tabular-nums">
                  {t.pct != null ? `${(t.pct * 100).toFixed(1)}%` : '—'}
                  <span className="ml-1 text-[11px] text-muted-foreground">
                    {t.value > 0 ? `${(t.value / 10000).toFixed(1)}万` : ''}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 新鲜度提示 */}
      {(navStale.length > 0 || data.no_nav_funds > 0) && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          {navStale.length > 0 && (
            <span>净值滞后超 4 天：{navStale.map(h => `${h.name}@${h.nav_as_of}`).join('、')}（周一自动全量刷或手动刷新）</span>
          )}
          {data.no_nav_funds > 0 && <span> {data.no_nav_funds} 只基金无净值数据</span>}
        </div>
      )}

      {/* 持仓明细表 */}
      <Card className="gap-2 p-4">
        <div className="text-sm font-medium">持仓明细（点击行进画像）</div>
        <div className="overflow-x-auto">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {['基金', 'YTD', '近1年', '回撤(1y)', '夏普(1y)', '份额', '市值', '净值@', '持仓报告期'].map(h => (
                  <TableHead key={h} className="h-8 whitespace-nowrap px-2 text-right text-xs">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.holdings.map(h => (
                <TableRow key={h.code} className="cursor-pointer" onClick={() => navigate(`/library/${h.code}`)}>
                  <TableCell className="whitespace-nowrap px-2 py-1.5">
                    <span className="font-medium">{h.name}</span>
                    <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">{h.code}</span>
                    {h.domain_tags.map(t => (
                      <Badge key={t} variant="secondary" className="ml-1 h-4 px-1 text-[10px]">{t}</Badge>
                    ))}
                  </TableCell>
                  <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(h.ret_ytd))}>{pct(h.ret_ytd)}</TableCell>
                  <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(h.ret_1y))}>{pct(h.ret_1y)}</TableCell>
                  <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', h.max_dd != null && h.max_dd < -0.30 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400')}>{pct(h.max_dd)}</TableCell>
                  <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneClass(h.sharpe))}>
                    {h.sharpe != null ? h.sharpe.toFixed(2) : '—'}
                  </TableCell>
                  <TableCell className="px-2 py-1.5 text-right tabular-nums">
                    {h.shares != null ? h.shares.toLocaleString() : <span className="text-[11px] text-muted-foreground">未录</span>}
                  </TableCell>
                  <TableCell className="px-2 py-1.5 text-right tabular-nums">
                    {h.market_value != null ? h.market_value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}
                  </TableCell>
                  <TableCell className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">{h.nav_as_of ?? '—'}</TableCell>
                  <TableCell className="px-2 py-1.5 text-right tabular-nums">
                    {h.holding_lag_days != null ? (
                      <span className={h.holding_lag_days > 120 ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}>
                        滞后{h.holding_lag_days}天
                      </span>
                    ) : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  )
}
