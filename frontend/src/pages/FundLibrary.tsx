import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createColumnHelper, tableFeatures, useTable } from '@tanstack/react-table'
import dayjs from 'dayjs'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Ellipsis, Plus, RefreshCw, Search, Trash2 } from 'lucide-react'
import { api, type Fund } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

// 画像库页（FR1）：持仓 + 研究池的录入与领域标签。
// 2026-10-19 重写：shadcn 风格定稿落地——侧栏工作台 + 紧凑表格 + KPI 卡。
// M1 骨架只做池管理；净值/收益等指标字段随 M2 摄取层接入后补到表格与详情页。
const DOMAIN_OPTIONS = ['AI算力', '医药', '黄金', '红利', '消费', 'QDII', '宽基']

const features = tableFeatures({})
const helper = createColumnHelper<typeof features, Fund>()

/* ---------- 入池弹窗：react-hook-form + zod（手动 safeParse，见定稿 §1） ---------- */

const fundFormSchema = z.object({
  code: z.string().regex(/^\d{6}$/, '6 位数字代码'),
  name: z.string().trim().min(1, '必填'),
  pool_type: z.enum(['holding', 'research']),
  domainTags: z.string(),
})
type FundFormValues = z.infer<typeof fundFormSchema>

const DEFAULT_FORM: FundFormValues = { code: '', name: '', pool_type: 'research', domainTags: '' }

function AddFundDialog({ open, onOpenChange, onDone }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDone: () => void
}) {
  const { register, handleSubmit, reset, setValue, watch, setError, formState: { errors } } =
    useForm<FundFormValues>({ defaultValues: DEFAULT_FORM })
  const [submitting, setSubmitting] = useState(false)

  const tags = watch('domainTags').split(/[,，\s]+/).filter(Boolean)
  const toggleTag = (tag: string) => {
    const next = tags.includes(tag) ? tags.filter(t => t !== tag) : [...tags, tag]
    setValue('domainTags', next.join(' '))
  }

  const submit = async (values: FundFormValues) => {
    const parsed = fundFormSchema.safeParse(values)
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        setError(issue.path[0] as keyof FundFormValues, { message: issue.message })
      }
      return
    }
    const domain_tags = parsed.data.domainTags.split(/[,，\s]+/).map(s => s.trim()).filter(Boolean)
    setSubmitting(true)
    try {
      const fund = await api.addFund({
        code: parsed.data.code,
        name: parsed.data.name,
        pool_type: parsed.data.pool_type,
        domain_tags,
      })
      toast.success(`${fund.name} 已入池`)
      reset(DEFAULT_FORM)
      onOpenChange(false)
      onDone()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>基金入池</DialogTitle>
          <DialogDescription>录入持仓或研究标的，领域标签后续用于领域探索聚合。</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(submit)} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="fund-code">基金代码</Label>
            <Input id="fund-code" inputMode="numeric" maxLength={6} placeholder="如 000390" className="tabular-nums" {...register('code')} />
            {errors.code && <p className="text-xs text-destructive">{errors.code.message}</p>}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="fund-name">基金名称</Label>
            <Input id="fund-name" placeholder="如 华商优势行业A" {...register('name')} />
            {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="fund-pool">入哪个池</Label>
            <Select value={watch('pool_type')} onValueChange={v => setValue('pool_type', v as FundFormValues['pool_type'])}>
              <SelectTrigger id="fund-pool" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="holding">持仓（实盘）</SelectItem>
                <SelectItem value="research">研究池（观察）</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="fund-tags">领域标签</Label>
            <Input id="fund-tags" placeholder="空格或逗号分隔，如：AI算力 黄金" {...register('domainTags')} />
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              {DOMAIN_OPTIONS.map(tag => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => toggleTag(tag)}
                  aria-pressed={tags.includes(tag)}
                  className={cn(
                    'h-6 rounded-md border px-2 text-xs transition-colors',
                    tags.includes(tag)
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
            <Button type="submit" disabled={submitting}>{submitting ? '提交中…' : '确认入池'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ---------- 行操作：移出（确认弹窗） ---------- */

function RowActions({ fund, onConfirm }: { fund: Fund; onConfirm: (fund: Fund) => void }) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-7 text-muted-foreground" aria-label={`${fund.name} 更多操作`}>
          <Ellipsis className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setConfirmOpen(true)}>
          <Trash2 /> 移出
        </DropdownMenuItem>
      </DropdownMenuContent>
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>移出 {fund.name}？</AlertDialogTitle>
            <AlertDialogDescription>
              从池中删除该基金记录；已写下的结论笔记与 md 快照会保留。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => onConfirm(fund)}>确认移出</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DropdownMenu>
  )
}

/* ---------- 页面 ---------- */

type PoolFilter = 'all' | 'holding' | 'research'

export default function FundLibrary() {
  const navigate = useNavigate()
  const [funds, setFunds] = useState<Fund[]>([])
  const [loading, setLoading] = useState(false)
  const [pool, setPool] = useState<PoolFilter>('all')
  const [query, setQuery] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      setFunds(await api.listFunds())
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void reload() }, [reload])

  const removeRef = useRef<(fund: Fund) => void>(() => {})
  const remove = async (fund: Fund) => {
    try {
      await api.removeFund(fund.code)
      toast.success(`${fund.name} 已移出`)
      void reload()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  removeRef.current = remove

  const columns = useMemo(() => helper.columns([
    helper.accessor('name', {
      header: '基金',
      cell: ctx => (
        <span className="whitespace-nowrap">
          <span className="font-medium">{ctx.row.original.name}</span>
          <span className="ml-2 text-xs text-muted-foreground tabular-nums">{ctx.row.original.code}</span>
        </span>
      ),
    }),
    helper.accessor('domain_tags', {
      header: '领域',
      cell: ctx => {
        const tags = ctx.row.original.domain_tags
        return tags.length > 0
          ? <span className="flex flex-wrap gap-1">{tags.map(t => <Badge key={t} variant="secondary" className="text-[11px]">{t}</Badge>)}</span>
          : <span className="text-muted-foreground">—</span>
      },
    }),
    helper.accessor('pool_type', {
      header: '池',
      cell: ctx => ctx.row.original.pool_type === 'holding'
        ? <Badge variant="outline">持仓</Badge>
        : <Badge variant="secondary">研究池</Badge>,
    }),
    helper.accessor('has_note', {
      header: '结论',
      cell: ctx => ctx.row.original.has_note
        ? <Badge variant="outline">已记</Badge>
        : <span className="text-xs text-muted-foreground">未记</span>,
    }),
    helper.accessor('created_at', {
      header: '入池时间',
      cell: ctx => <span className="tabular-nums text-muted-foreground">{dayjs(ctx.row.original.created_at).format('YYYY-MM-DD')}</span>,
    }),
    helper.display({
      id: 'actions',
      cell: ctx => <RowActions fund={ctx.row.original} onConfirm={f => removeRef.current(f)} />,
    }),
  ]), [])

  const data = useMemo(() => {
    const q = query.trim()
    return funds.filter(f =>
      (pool === 'all' || f.pool_type === pool)
      && (!q || f.name.includes(q) || f.code.includes(q)),
    )
  }, [funds, pool, query])

  const table = useTable({ features, columns, data })

  const holdings = funds.filter(f => f.pool_type === 'holding').length
  const research = funds.filter(f => f.pool_type === 'research').length
  const noted = funds.filter(f => f.has_note).length

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">画像库</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">持仓、研究池与观察标的的基金档案</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="size-9" onClick={() => void reload()} disabled={loading} aria-label="刷新">
            <RefreshCw className={cn('size-4', loading && 'animate-spin')} />
          </Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" /> 基金入池
          </Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="gap-0 p-4">
          <div className="text-xs text-muted-foreground">持仓基金</div>
          <div className="mt-1.5 text-[22px] font-semibold tabular-nums">{holdings} 只</div>
          <div className="mt-0.5 text-xs text-muted-foreground">实盘持有</div>
        </Card>
        <Card className="gap-0 p-4">
          <div className="text-xs text-muted-foreground">研究池</div>
          <div className="mt-1.5 text-[22px] font-semibold tabular-nums">{research} 只</div>
          <div className="mt-0.5 text-xs text-muted-foreground">观察候选</div>
        </Card>
        <Card className="gap-0 p-4">
          <div className="text-xs text-muted-foreground">结论已记</div>
          <div className="mt-1.5 text-[22px] font-semibold tabular-nums">{noted} <span className="text-sm font-normal text-muted-foreground">/ {funds.length}</span></div>
          <div className="mt-0.5 text-xs text-muted-foreground">全部基金</div>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={pool} onValueChange={v => setPool(v as PoolFilter)}>
          <TabsList className="h-8">
            <TabsTrigger value="all" className="text-xs">全部</TabsTrigger>
            <TabsTrigger value="holding" className="text-xs">持仓</TabsTrigger>
            <TabsTrigger value="research" className="text-xs">研究池</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索基金 / 代码"
            aria-label="搜索基金或代码"
            className="h-8 w-56 pl-8"
          />
        </div>
      </div>

      {loading && funds.length === 0 ? (
        <div className="rounded-xl border bg-card">
          <div className="border-b p-3"><Skeleton className="h-4 w-40" /></div>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="border-b p-3 last:border-b-0"><Skeleton className="h-5 w-full" /></div>
          ))}
        </div>
      ) : funds.length === 0 ? (
        <div className="grid place-items-center rounded-xl border border-dashed bg-card/50 py-20 text-center">
          <div className="flex flex-col items-center gap-3">
            <h3 className="text-sm font-semibold">库还是空的</h3>
            <p className="max-w-sm text-sm text-muted-foreground">
              从右上角「基金入池」录入第一只基金——先录 5 只持仓，研究池 7 只名单见调查报告附录 A。
            </p>
            <Button variant="outline" onClick={() => setDialogOpen(true)}>
              <Plus className="size-4" /> 基金入池
            </Button>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table className="text-[13px]">
            <TableHeader>
              {table.getHeaderGroups().map(group => (
                <TableRow key={group.id} className="hover:bg-transparent">
                  {group.headers.map(header => (
                    <TableHead key={header.id} className="h-9 whitespace-nowrap px-3 text-xs">
                      {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={columns.length} className="py-10 text-center text-muted-foreground">
                    当前筛选无结果
                  </TableCell>
                </TableRow>
              ) : table.getRowModel().rows.map(row => (
                <TableRow
                  key={row.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/library/${row.original.code}`)}
                >
                  {row.getAllCells().map(cell => (
                    <TableCell
                      key={cell.id}
                      className="px-3 py-2"
                      onClick={cell.column.id === 'actions' ? e => e.stopPropagation() : undefined}
                    >
                      <table.FlexRender cell={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddFundDialog open={dialogOpen} onOpenChange={setDialogOpen} onDone={() => void reload()} />
    </div>
  )
}
