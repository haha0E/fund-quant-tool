import { Badge } from '@/components/ui/badge'

// M3-M5 逐页替换：仪表盘(M3) / 领域探索(M5) / 组合评估(M3) / 穿透分析(M4)
export default function Placeholder({ title, milestone }: { title: string; milestone: string }) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed bg-card/50 py-28 text-center">
      <div className="flex flex-col items-center gap-2.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-sm text-muted-foreground">骨架就位，内容随 {milestone} 交付逐步长出来。</p>
        <Badge variant="secondary">{milestone} 交付</Badge>
      </div>
    </div>
  )
}
