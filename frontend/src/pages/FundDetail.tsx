import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { toast } from 'sonner'
import {
  ArrowLeft, CircleHelp, Database, RefreshCw, Save,
} from 'lucide-react'
import { api, METRIC_TOOLTIPS, type FundDetail as Detail } from '@/api/client'
import { EChart } from '@/components/EChart'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// 单基金画像页（M2）：净值/回撤图 + 指标表 + 档案 20 字段 + 前十持仓 + 结论编辑。
// 口径文案与 backend/app/services/metrics.py 保持同义（实现方案 §6 强制写入界面）。

type Window = '1m' | '3m' | '6m' | 'ytd' | '1y' | 'all'
const WINDOW_DAYS: Record<Window, number | null> = {
  '1m': 30, '3m': 90, '6m': 180, ytd: null, '1y': 365, all: null,
}

const WINDOW_LABELS: Record<Window, string> = {
  '1m': '1月', '3m': '3月', '6m': '6月', ytd: 'YTD', '1y': '1年', all: '全部',
}

function pct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

function num(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(2)}`
}

// 红涨绿跌（中国市场习惯）
function toneClass(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'text-foreground'
  return v > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
}

/* ---------- 图表：窗内分红重构回撤（§6-3，与后端口径一致） ---------- */

function buildChartOption(detail: Detail, win: Window) {
  const nav = detail.nav
  if (nav.length === 0) return {}
  const last = nav[nav.length - 1].date
  let start: string
  if (win === 'ytd') start = `${last.slice(0, 4)}-01-01`
  else if (win === 'all') start = nav[0].date
  else {
    const d = dayjs(last).subtract(WINDOW_DAYS[win]!, 'day')
    start = d.format('YYYY-MM-DD')
  }
  let i0 = nav.findIndex(p => p.date >= start)
  if (i0 < 0) i0 = 0
  if (i0 > 0) i0 -= 1 // 窗口基线含前一日，保证窗内首日有涨跌参照
  const slice = nav.slice(i0)
  const dates = slice.map(p => p.date)
  const unit = slice.map(p => p.unit_nav)

  // 窗内累计分红重构 → 回撤序列
  let cum = 0
  const adj = slice.map(p => { cum += p.dividend; return p.unit_nav + cum })
  let peak = -Infinity
  const dd = adj.map(v => { peak = Math.max(peak, v); return +(v / peak - 1).toFixed(6) })

  const divMarks = slice
    .filter(p => p.dividend > 0)
    .map(p => ({ coord: [p.date, p.unit_nav], value: `分红 ${p.dividend}`, symbolSize: 1 }))

  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', confine: true },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 52, right: 16, top: 16, height: '52%' },
      { left: 52, right: 16, top: '74%', height: '20%' },
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
        axisLabel: { color: '#888', fontSize: 10, formatter: (v: number) => v.toFixed(3) },
        splitLine: { lineStyle: { color: '#8883' } },
      },
      {
        type: 'value', gridIndex: 1, max: 0,
        axisLabel: {
          color: '#888', fontSize: 10,
          formatter: (v: number) => `${(v * 100).toFixed(0)}%`,
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '单位净值', type: 'line', data: unit, xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, lineStyle: { width: 1.6, color: '#2563eb' },
        itemStyle: { color: '#2563eb' },
        markPoint: {
          symbol: 'pin', symbolSize: 44,
          itemStyle: { color: '#f59e0b' },
          label: { fontSize: 9, color: '#fff' },
          data: divMarks,
        },
      },
      {
        name: '回撤', type: 'line', data: dd, xAxisIndex: 1, yAxisIndex: 1,
        showSymbol: false, lineStyle: { width: 1.2, color: '#16a34a' },
        areaStyle: { color: 'rgba(22,163,74,0.18)' },
        itemStyle: { color: '#16a34a' },
      },
    ],
  }
}

/* ---------- 指标卡 ---------- */

function MetricCard({ label, value, tooltip, className }: {
  label: string
  value: string
  tooltip: string
  className?: string
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

/* ---------- 档案字段表 ---------- */

const PROFILE_LAYOUT: { key: keyof NonNullable<Detail['profile']>; label: string; wide?: boolean }[] = [
  { key: 'fund_type', label: '基金类型' },
  { key: 'manager', label: '基金经理' },
  { key: 'scale', label: '最新规模' },
  { key: 'inception_date', label: '成立日期' },
  { key: 'company', label: '基金公司' },
  { key: 'custodian', label: '托管银行' },
  { key: 'rating', label: '基金评级' },
  { key: 'tracked_index', label: '跟踪标的' },
  { key: 'fee_management', label: '管理费率', },
  { key: 'fee_custody', label: '托管费率' },
  { key: 'fee_subscription', label: '申购费率(高)' },
  { key: 'fee_redemption', label: '赎回费率(高)' },
  { key: 'stock_position', label: '股票仓位' },
  { key: 'stock_position_as_of', label: '仓位报告期' },
  { key: 'benchmark', label: '业绩比较基准', wide: true },
  { key: 'objective', label: '投资目标', wide: true },
  { key: 'full_name', label: '基金全称', wide: true },
]

function fmtProfileValue(key: string, v: unknown): string {
  if (v == null || v === '') return '—（未披露）'
  if (['fee_management', 'fee_custody', 'fee_subscription', 'fee_redemption'].includes(key))
    return `${v as number}%`
  if (key === 'stock_position') return `${v as number}%`
  return String(v)
}

/* ---------- 页面 ---------- */

export default function FundDetail() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [win, setWin] = useState<Window>('1y')
  const [noteDraft, setNoteDraft] = useState<string | null>(null)
  const [savingNote, setSavingNote] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const d = await api.getFundDetail(code)
      setDetail(d)
      setNoteDraft(null)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [code])

  useEffect(() => { void reload() }, [reload])

  const doRefresh = async () => {
    setRefreshing(true)
    toast.info('正在刷新净值/档案/持仓（反爬限速，约 15-30 秒）…')
    try {
      const r = await api.refresh('all', code)
      if (Object.keys(r.errors).length > 0) {
        toast.warning(`刷新完成，但部分数据源失败：${Object.entries(r.errors).map(([k, v]) => `${k}: ${v}`).join('；').slice(0, 120)}`)
      } else {
        toast.success('数据已刷新')
      }
      await reload()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRefreshing(false)
    }
  }

  const saveNote = async () => {
    if (noteDraft == null) return
    setSavingNote(true)
    try {
      await api.saveNote(code, noteDraft)
      toast.success('结论已保存（md 快照已双写 data/notes/）')
      await reload()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSavingNote(false)
    }
  }

  const chartOption = useMemo(
    () => (detail ? buildChartOption(detail, win) : {}),
    [detail, win],
  )

  const reportLagDays = useMemo(() => {
    if (!detail?.holdings.length) return null
    return dayjs().diff(dayjs(detail.holdings[0].report_date), 'day')
  }, [detail])

  if (loading && !detail) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-72" />
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[72px]" />)}</div>
        <Skeleton className="h-[360px]" />
      </div>
    )
  }
  if (!detail) return null

  const m = detail.metric
  const noteValue = noteDraft ?? detail.note
  const noteDirty = noteDraft != null && noteDraft !== detail.note

  return (
    <div className="flex flex-col gap-4">
      {/* 头部 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="icon" className="mt-0.5 size-8" onClick={() => navigate('/library')} aria-label="返回画像库">
            <ArrowLeft className="size-4" />
          </Button>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold">{detail.name || detail.code}</h1>
              <span className="text-sm text-muted-foreground tabular-nums">{detail.code}</span>
              {detail.pool_type === 'holding'
                ? <Badge variant="outline">持仓</Badge>
                : <Badge variant="secondary">研究池</Badge>}
              {detail.domain_tags.map(t => <Badge key={t} variant="secondary" className="text-[11px]">{t}</Badge>)}
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {m?.as_of ? `净值截止 ${m.as_of}` : '净值未摄取'}
              {detail.profile?.as_of ? ` · 档案 @ ${detail.profile.as_of}` : ''}
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => void doRefresh()} disabled={refreshing}>
          <RefreshCw className={cn('size-4', refreshing && 'animate-spin')} />
          {refreshing ? '刷新中…' : '刷新数据'}
        </Button>
      </div>

      {/* 数据缺口（不静默造假） */}
      {detail.data_gaps.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <span className="font-medium">数据缺口：</span>{detail.data_gaps.join('；')}
        </div>
      )}

      {/* 指标卡 */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <MetricCard label="近1月" value={pct(m?.ret_1m)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_1m)} />
        <MetricCard label="近3月" value={pct(m?.ret_3m)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_3m)} />
        <MetricCard label="近6月" value={pct(m?.ret_6m)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_6m)} />
        <MetricCard label="今年以来" value={pct(m?.ret_ytd)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_ytd)} />
        <MetricCard label="近1年" value={pct(m?.ret_1y)} tooltip={METRIC_TOOLTIPS.ret} className={toneClass(m?.ret_1y)} />
        <MetricCard label="年化收益(1y)" value={pct(m?.ann_ret)} tooltip={METRIC_TOOLTIPS.ann_ret} className={toneClass(m?.ann_ret)} />
        <MetricCard label="最大回撤(1y)" value={pct(m?.max_dd)} tooltip={METRIC_TOOLTIPS.max_dd} className="text-green-600 dark:text-green-400" />
        <MetricCard label="年化波动(1y)" value={pct(m?.ann_vol)} tooltip={METRIC_TOOLTIPS.ann_vol} />
        <MetricCard label="夏普(1y)" value={num(m?.sharpe)} tooltip={METRIC_TOOLTIPS.sharpe} className={toneClass(m?.sharpe)} />
      </div>

      {/* 净值/回撤图 */}
      <Card className="gap-2 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-medium">单位净值与回撤</div>
          <Tabs value={win} onValueChange={v => setWin(v as Window)}>
            <TabsList className="h-7">
              {(Object.keys(WINDOW_LABELS) as Window[]).map(k => (
                <TabsTrigger key={k} value={k} className="h-6 px-2 text-xs">{WINDOW_LABELS[k]}</TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
        {detail.nav.length > 0
          ? <EChart option={chartOption} height={340} />
          : <div className="grid h-40 place-items-center text-sm text-muted-foreground">净值未摄取，点右上「刷新数据」拉取</div>}
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          回撤按「单位净值+窗内累计分红」重构后取 running max 最深跌幅（切窗口即时重算，与指标表同口径）；
          橙色标记为分红事件（每份现金）。累计净值仅作分红核对常数，不入图（§6 口径）。
        </p>
      </Card>

      {/* 档案 20 字段 + 持仓 */}
      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="gap-3 p-4 xl:col-span-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">基金档案（{detail.profile ? '20 字段自动填充' : '未摄取'}）</div>
            {detail.profile?.source && (
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Database className="size-3" />{detail.profile.source}
              </span>
            )}
          </div>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            {PROFILE_LAYOUT.map(({ key, label, wide }) => (
              <div key={key} className={cn('flex items-baseline justify-between gap-3 border-b border-dashed py-1', wide && 'sm:col-span-2')}>
                <dt className="shrink-0 text-xs text-muted-foreground">{label}</dt>
                <dd className="min-w-0 text-right text-[13px]" title={fmtProfileValue(key, detail.profile?.[key])}>
                  {fmtProfileValue(key, detail.profile?.[key])}
                </dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card className="gap-3 p-4 xl:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium">前十大持仓</div>
            {detail.holdings.length > 0 && (
              <span className="flex items-center gap-1.5">
                <Badge variant="outline" className="text-[11px] tabular-nums">{detail.holdings[0].report_date}</Badge>
                {(reportLagDays ?? 0) > 60 && (
                  <Badge className="bg-amber-500/15 text-[11px] text-amber-700 border border-amber-500/40 dark:text-amber-400">
                    报告期滞后 {reportLagDays} 天
                  </Badge>
                )}
              </span>
            )}
          </div>
          {detail.holdings.length > 0 ? (
            <Table className="text-[13px]">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-8 px-2 text-xs">股票</TableHead>
                  <TableHead className="h-8 px-2 text-right text-xs">代码</TableHead>
                  <TableHead className="h-8 px-2 text-right text-xs">占净值比</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.holdings.map(h => (
                  <TableRow key={h.stock_code}>
                    <TableCell className="px-2 py-1.5">{h.stock_name}</TableCell>
                    <TableCell className="px-2 py-1.5 text-right tabular-nums text-muted-foreground">{h.stock_code}</TableCell>
                    <TableCell className="px-2 py-1.5 text-right tabular-nums">
                      {h.weight.toFixed(2)}%
                      <span className="ml-1.5 inline-block h-1.5 rounded-sm bg-primary/60 align-middle" style={{ width: `${Math.min(h.weight * 4, 60)}px` }} aria-hidden />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="grid h-40 place-items-center text-sm text-muted-foreground">持仓未披露或未摄取</div>
          )}
          <p className="text-[11px] text-muted-foreground">前十大持仓为定期报告截面，较净值滞后一个季度左右属正常。</p>
        </Card>
      </div>

      {/* 结论层 */}
      <Card className="gap-2 p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">结论层（手写 markdown，保存时双写 data/notes/{code}.md）</div>
          {detail.note_updated_at && <span className="text-[11px] text-muted-foreground">更新于 {detail.note_updated_at.slice(0, 16)}</span>}
        </div>
        <Textarea
          value={noteValue}
          onChange={e => setNoteDraft(e.target.value)}
          placeholder={'例如：## 核心判断\n- 光模块暴露高，三季报关注减仓信号\n- 操作：等 10-28 三季报再定'}
          className="min-h-40 font-mono text-[13px]"
        />
        <div className="flex justify-end">
          <Button size="sm" onClick={() => void saveNote()} disabled={!noteDirty || savingNote}>
            <Save className="size-4" />{savingNote ? '保存中…' : '保存结论'}
          </Button>
        </div>
      </Card>
    </div>
  )
}
