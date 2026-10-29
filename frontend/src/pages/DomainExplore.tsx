import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Compass, Search } from 'lucide-react'
import { api, type ExploreCandidate, type ExploreDomain } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

// 领域探索页（M5，PRD FR1 入池机制）：选领域 → 候选列表（快照映射 > 池内标签 > 排行粗筛）
// → 入研究池并自动单刷。收益列为数据商区间涨幅（%），仅粗筛排序；入池后一律库内 §6 自算。

function pctS(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
}

function toneS(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 1e-9) return 'text-foreground'
  return v > 0 ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'
}

const SOURCE_BADGE: Record<string, string> = {
  '快照映射': 'border-primary/50 text-primary',
  '池内标签': 'border-border text-muted-foreground',
  '排行粗筛': 'border-border text-muted-foreground',
}

export default function DomainExplore() {
  const [domains, setDomains] = useState<ExploreDomain[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const [candidates, setCandidates] = useState<ExploreCandidate[] | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [pooling, setPooling] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.listExploreDomains()
        setDomains(list)
      } catch (e) {
        toast.error((e as Error).message)
      }
    })()
  }, [])

  const open = useCallback(async (domain: string) => {
    setCurrent(domain)
    setCandidates(null)
    setLoading(true)
    try {
      const d = await api.exploreDomain(domain)
      setCandidates(d.candidates)
      setWarning(d.warning ?? null)
    } catch (e) {
      toast.error((e as Error).message)
      setCandidates([])
    } finally {
      setLoading(false)
    }
  }, [])

  const addToPool = async (c: ExploreCandidate, domain: string) => {
    setPooling(c.code)
    try {
      const fund = await api.addExplorePool(c.code, [domain])
      toast.success(`${fund.name} 已入研究池，正在单刷数据（约 15-30 秒）…`)
      try {
        const r = await api.refresh('all', c.code)
        if (Object.keys(r.errors).length > 0) {
          toast.warning(`部分数据源失败：${Object.entries(r.errors).map(([k, v]) => `${k}: ${v}`).join('；').slice(0, 100)}`)
        } else {
          toast.success('数据已就绪，画像库可见')
        }
      } catch (e) {
        toast.warning(`入池成功但刷新失败：${(e as Error).message}（详情页可手动刷新）`)
      }
      await open(domain)  // 刷新列表的 in_pool 状态
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setPooling(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">领域探索</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            选领域看候选基金（快照映射优先，排行关键词兜底），一键入研究池并自动单刷
          </p>
        </div>
      </div>

      {/* 领域选择 */}
      <Card className="flex flex-wrap gap-1.5 p-3">
        {domains.map(d => (
          <button
            key={d.domain}
            type="button"
            onClick={() => void open(d.domain)}
            aria-pressed={current === d.domain}
            className={cn(
              'flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[13px] transition-colors',
              current === d.domain
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            {d.domain}
            <span className={cn(
              'rounded px-1 text-[10px] tabular-nums',
              current === d.domain ? 'bg-primary-foreground/20' : 'bg-muted',
            )}>
              {d.snapshot_funds > 0 ? `快照${d.snapshot_funds} ` : ''}池{d.pool_funds}
            </span>
          </button>
        ))}
        {domains.length === 0 && <Skeleton className="h-8 w-64" />}
      </Card>

      {warning && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          {warning}
        </div>
      )}

      {!current ? (
        <Card className="grid place-items-center py-20 text-center text-sm text-muted-foreground">
          <div className="flex flex-col items-center gap-2">
            <Compass className="size-5 opacity-50" aria-hidden />
            选一个领域开始探索（候选 = 快照映射 + 池内标签 + 排行关键词粗筛）
          </div>
        </Card>
      ) : loading || candidates == null ? (
        <div className="rounded-xl border bg-card">
          <div className="border-b p-3"><Skeleton className="h-4 w-48" /></div>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="border-b p-3 last:border-b-0"><Skeleton className="h-5 w-full" /></div>
          ))}
        </div>
      ) : (
        <Card className="gap-2 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">{current} · 候选 {candidates.length} 只（近1年降序）</div>
            <Button variant="ghost" size="sm" onClick={() => void open(current)} aria-label="刷新列表">
              <Search className="size-3.5" />重查
            </Button>
          </div>
          <div className="overflow-x-auto">
            <Table className="text-[13px]">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {['基金', '来源', '近1月', '近3月', '近6月', '近1年', '今年以来', ''].map(h => (
                    <TableHead key={h} className="h-8 whitespace-nowrap px-2 text-right text-xs">{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.map(c => (
                  <TableRow key={c.code} className={cn(c.in_pool && 'opacity-75')}>
                    <TableCell className="whitespace-nowrap px-2 py-1.5">
                      <span className="font-medium">{c.name || c.code}</span>
                      <span className="ml-1.5 text-[11px] text-muted-foreground tabular-nums">{c.code}</span>
                    </TableCell>
                    <TableCell className="px-2 py-1.5 text-right">
                      <Badge variant="outline" className={cn('text-[10px]', SOURCE_BADGE[c.source])}>
                        {c.source}
                      </Badge>
                    </TableCell>
                    <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneS(c.ret_1m))}>{pctS(c.ret_1m)}</TableCell>
                    <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneS(c.ret_3m))}>{pctS(c.ret_3m)}</TableCell>
                    <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneS(c.ret_6m))}>{pctS(c.ret_6m)}</TableCell>
                    <TableCell className={cn('px-2 py-1.5 text-right font-medium tabular-nums', toneS(c.ret_1y))}>{pctS(c.ret_1y)}</TableCell>
                    <TableCell className={cn('px-2 py-1.5 text-right tabular-nums', toneS(c.ret_ytd))}>{pctS(c.ret_ytd)}</TableCell>
                    <TableCell className="px-2 py-1.5 text-right">
                      {c.in_pool ? (
                        <Badge variant="secondary" className="text-[10px]">已在池</Badge>
                      ) : (
                        <Button
                          size="sm" variant="outline" className="h-6 px-2 text-[11px]"
                          onClick={() => void addToPool(c, current)}
                          disabled={pooling === c.code}
                        >
                          {pooling === c.code ? '入池刷新中…' : '入研究池'}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            收益列为数据商（东财排行）区间涨幅，仅用于候选粗筛排序；入池后的画像指标一律以库内
            §6 口径自算（现金分红收益/自算年化）。快照映射来自 ZCode 周更领域表（可信度最高）。
          </p>
        </Card>
      )}
    </div>
  )
}
