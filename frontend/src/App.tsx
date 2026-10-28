import { Component, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { SiteHeader } from '@/components/layout/site-header'
import { AUTH_REQUIRED_EVENT, setToken } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import FundLibrary from '@/pages/FundLibrary'
import FundDetail from '@/pages/FundDetail'
import Portfolio from '@/pages/Portfolio'
import Strategy from '@/pages/Strategy'
import Overlap from '@/pages/Overlap'
import Placeholder from '@/pages/Placeholder'

// 写接口 token 补录弹窗（M3 鉴权）：401 全局事件触发，粘贴一次存 localStorage
function TokenDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [value, setValue] = useState('')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>写接口鉴权</DialogTitle>
          <DialogDescription>
            写操作（入池/刷新/保存）需要 token。完整 token 见电脑上
            data/auth_token.txt，粘贴一次即可。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label htmlFor="fqt-token">X-FQT-Token</Label>
          <Input id="fqt-token" value={value} onChange={e => setValue(e.target.value)}
            placeholder="粘贴 data/auth_token.txt 内容" className="font-mono text-xs" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={() => { setToken(value); onOpenChange(false) }}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// 顶层错误边界：任何渲染异常显示错误卡（含报错信息与重载按钮），不再整页白屏
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="grid min-h-screen place-items-center bg-background p-6 text-foreground">
          <div className="flex max-w-md flex-col items-center gap-3 rounded-xl border bg-card p-6 text-center">
            <h2 className="text-base font-semibold">页面出错了</h2>
            <p className="break-all text-xs leading-relaxed text-muted-foreground">
              {String(this.state.error?.message ?? this.state.error)}
            </p>
            <Button size="sm" onClick={() => window.location.reload()}>重新加载</Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

// 应用壳：侧边栏 + 顶栏 + 路由主区（界面风格定稿 2026-10-19）
export default function App() {
  const [tokenOpen, setTokenOpen] = useState(false)

  useEffect(() => {
    const onAuth = () => setTokenOpen(true)
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuth)
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuth)
  }, [])

  return (
    <ErrorBoundary>
      <TooltipProvider delayDuration={150}>
        <div className="flex min-h-screen w-full bg-background text-foreground">
          <AppSidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <SiteHeader />
            <main className="min-w-0 flex-1 p-6">
              <Routes>
                <Route path="/" element={<Navigate to="/library" replace />} />
                <Route path="/dashboard" element={<Placeholder title="仪表盘" milestone="M5" />} />
                <Route path="/library" element={<FundLibrary />} />
                <Route path="/library/:code" element={<FundDetail />} />
                <Route path="/domain" element={<Placeholder title="领域探索" milestone="M5" />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/strategy" element={<Strategy />} />
                <Route path="/overlap" element={<Overlap />} />
              </Routes>
            </main>
          </div>
          <Toaster richColors position="top-center" />
          <TokenDialog open={tokenOpen} onOpenChange={setTokenOpen} />
        </div>
      </TooltipProvider>
    </ErrorBoundary>
  )
}
