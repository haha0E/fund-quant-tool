import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ChevronsLeft, ChevronsRight, TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { NAV_GROUPS } from '@/lib/nav'

const SIDEBAR_KEY = 'fw-sidebar'

function loadCollapsed(): boolean {
  return localStorage.getItem(SIDEBAR_KEY) === 'collapsed'
}

// 侧边栏工作台骨架（界面风格定稿 §4）：可折叠成 56px 图标栏，窄屏自动收起。
// 数据源与净值截止时间：M2 摄取层接入后在底部展示（缺省隐藏）。
export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(loadCollapsed)

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? 'collapsed' : 'expanded')
  }, [collapsed])

  return (
    <aside
      className={cn(
        'sticky top-0 flex h-screen shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200',
        collapsed ? 'w-14' : 'w-56',
        'max-md:w-14',
      )}
    >
      <div className={cn('flex items-center gap-2.5 px-3 py-4', collapsed && 'justify-center px-0', 'max-md:justify-center max-md:px-0')}>
        <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
          <TrendingUp className="size-4" aria-hidden="true" />
        </span>
        <span className={cn('whitespace-nowrap text-sm font-semibold tracking-wide', collapsed && 'hidden', 'max-md:hidden')}>
          基金研究工作台
        </span>
      </div>

      <nav aria-label="主导航" className="flex flex-1 flex-col gap-1 px-2">
        {NAV_GROUPS.map(group => (
          <div key={group.label}>
            <div
              className={cn('px-2.5 pb-1 pt-4 text-[11.5px] text-muted-foreground', collapsed && 'text-center', 'max-md:text-center')}
            >
              {collapsed ? '·' : group.label}
            </div>
            {group.items.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground',
                    isActive && 'bg-sidebar-accent font-medium text-sidebar-foreground',
                    collapsed && 'justify-center px-0',
                    'max-md:justify-center max-md:px-0',
                  )
                }
                title={collapsed ? item.label : undefined}
              >
                <item.icon className="size-4 shrink-0" aria-hidden="true" />
                <span className={cn('whitespace-nowrap', collapsed && 'hidden', 'max-md:hidden')}>{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-1 p-2">
        {/* 数据源 · 净值截至：M2 摄取层接入后在此展示 */}
        <Button
          variant="ghost"
          size="icon"
          className="size-8 self-center text-muted-foreground"
          onClick={() => setCollapsed(c => !c)}
          aria-label={collapsed ? '展开侧栏' : '折叠侧栏'}
        >
          {collapsed ? <ChevronsRight className="size-4" /> : <ChevronsLeft className="size-4" />}
        </Button>
      </div>
    </aside>
  )
}
