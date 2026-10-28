import { useCallback, useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { marked } from 'marked'
import { toast } from 'sonner'
import { FileText, RefreshCw } from 'lucide-react'
import { api, type StrategyContent, type StrategyFile } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// 策略页（M3）：固化策略 + 双周 brief 只读渲染。
// 内容全部来自 data/strategy/ 下 git 管理的 md——版本史看 git diff，页面不改写。
// 渲染用 marked：内容是本仓库自有文件（非用户输入），仅做 script 剥离兜底。

function renderMd(md: string): string {
  const html = marked.parse(md, { async: false }) as string
  return html.replace(/<script[\s\S]*?<\/script>/gi, '')
}

export default function Strategy() {
  const [files, setFiles] = useState<StrategyFile[]>([])
  const [current, setCurrent] = useState<StrategyContent | null>(null)
  const [loading, setLoading] = useState(false)

  const open = useCallback(async (filename: string) => {
    setLoading(true)
    try {
      setCurrent(await api.getStrategy(filename))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const reload = useCallback(async () => {
    try {
      const list = await api.listStrategy()
      setFiles(list)
      if (list.length > 0 && !list.some(f => f.filename === current?.filename)) {
        await open(list[0].filename)
      }
    } catch (e) {
      toast.error((e as Error).message)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.filename, open])

  useEffect(() => { void reload() }, [reload])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">策略</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            固化纪律与双周 brief（只读；修订走电脑端 git commit，版本史看 git diff）
          </p>
        </div>
        <Button variant="ghost" size="icon" className="size-9" onClick={() => void reload()} aria-label="刷新">
          <RefreshCw className="size-4" />
        </Button>
      </div>

      {files.length === 0 ? (
        <div className="grid place-items-center rounded-xl border border-dashed bg-card/50 py-20 text-center text-sm text-muted-foreground">
          data/strategy/ 下还没有 md（固定文件名 strategy.md + brief-YYYYMMDD.md）
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-4">
          <Card className="gap-1 p-2 lg:col-span-1">
            {files.map(f => (
              <button
                key={f.filename}
                type="button"
                onClick={() => void open(f.filename)}
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-muted',
                  current?.filename === f.filename && 'bg-muted',
                )}
              >
                <span className="flex w-full items-center gap-1.5 text-[13px] font-medium">
                  <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="truncate">{f.title}</span>
                </span>
                <span className="pl-5 text-[11px] text-muted-foreground tabular-nums">
                  {f.filename === 'strategy.md' && <Badge variant="secondary" className="mr-1 h-4 px-1 text-[10px]">固定</Badge>}
                  {dayjs(f.updated_at).format('YYYY-MM-DD HH:mm')}
                </span>
              </button>
            ))}
          </Card>

          <Card className="min-h-72 p-5 lg:col-span-3">
            {loading && !current ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-7 w-64" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/6" />
              </div>
            ) : current ? (
              <>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b pb-3">
                  <h2 className="text-base font-semibold">{current.title}</h2>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {current.filename} · 更新于 {dayjs(current.updated_at).format('YYYY-MM-DD HH:mm')}
                  </span>
                </div>
                <div
                  className="md-body"
                  // 内容为仓库自有 md（marked 渲染 + script 剥离），非用户输入
                  dangerouslySetInnerHTML={{ __html: renderMd(current.content) }}
                />
              </>
            ) : null}
          </Card>
        </div>
      )}
    </div>
  )
}
