import { useLocation } from 'react-router-dom'
import { ThemeToggle } from '@/components/layout/theme-toggle'
import { NAV_FLAT } from '@/lib/nav'

// 顶栏（定稿 §4）：面包屑 + 主题切换。数据截止时间随 M2 摄取层补充。
export function SiteHeader() {
  const { pathname } = useLocation()
  const current = NAV_FLAT.find(item => item.to === pathname)

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background px-6">
      <nav aria-label="面包屑" className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
        <span>工作台</span>
        <span className="opacity-60">/</span>
        <span className={current ? 'font-medium text-foreground' : undefined}>
          {current?.label ?? ''}
        </span>
      </nav>
      <ThemeToggle />
    </header>
  )
}
