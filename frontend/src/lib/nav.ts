import { BookOpen, Compass, LayoutDashboard, Library, PieChart, Share2, type LucideIcon } from 'lucide-react'

// 页面结构对应 PRD FR4：仪表盘 + 四个子页（画像库/领域探索/组合评估/穿透分析）
export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  milestone?: string
}

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: '研究',
    items: [
      { to: '/dashboard', label: '仪表盘', icon: LayoutDashboard },
      { to: '/library', label: '画像库', icon: Library },
      { to: '/strategy', label: '策略', icon: BookOpen },
      { to: '/domain', label: '领域探索', icon: Compass },
    ],
  },
  {
    label: '分析',
    items: [
      { to: '/portfolio', label: '组合评估', icon: PieChart },
      { to: '/overlap', label: '穿透分析', icon: Share2, milestone: 'M4' },
    ],
  },
]

export const NAV_FLAT: NavItem[] = NAV_GROUPS.flatMap(g => g.items)
