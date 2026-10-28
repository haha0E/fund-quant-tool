import { Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { SiteHeader } from '@/components/layout/site-header'
import FundLibrary from '@/pages/FundLibrary'
import FundDetail from '@/pages/FundDetail'
import Placeholder from '@/pages/Placeholder'

// 应用壳：侧边栏 + 顶栏 + 路由主区（界面风格定稿 2026-10-19）
export default function App() {
  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex min-h-screen w-full bg-background text-foreground">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <SiteHeader />
          <main className="min-w-0 flex-1 p-6">
            <Routes>
              <Route path="/" element={<Navigate to="/library" replace />} />
              <Route path="/dashboard" element={<Placeholder title="仪表盘" milestone="M3" />} />
              <Route path="/library" element={<FundLibrary />} />
              <Route path="/library/:code" element={<FundDetail />} />
              <Route path="/domain" element={<Placeholder title="领域探索" milestone="M5" />} />
              <Route path="/portfolio" element={<Placeholder title="组合评估" milestone="M3" />} />
              <Route path="/overlap" element={<Placeholder title="穿透分析" milestone="M4" />} />
            </Routes>
          </main>
        </div>
        <Toaster richColors position="top-center" />
      </div>
    </TooltipProvider>
  )
}
