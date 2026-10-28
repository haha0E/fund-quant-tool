import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { HeatmapChart, LineChart } from 'echarts/charts'
import {
  AxisPointerComponent, GridComponent, MarkPointComponent, TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// 按需注册（bundle 瘦身主点，配合后端 gzip）。
// 新图表类型/组件（柱状、dataZoom、legend…）用到时必须在此补注册，否则 setOption 静默不渲染。
echarts.use([
  LineChart, HeatmapChart, GridComponent, TooltipComponent, AxisPointerComponent,
  MarkPointComponent, VisualMapComponent, CanvasRenderer,
])

// 极简 ECharts React 封装：echarts-for-react@3.0.6 在 React 18 StrictMode
// 双挂载下画布尺寸不可靠（实测 canvas 宽 0/丢失），改用官方 API 自管生命周期。
// StrictMode 安全：卸载彻底 dispose，二次挂载重新 init；ResizeObserver 兜底容器尺寸。
export function EChart({ option, height = 340, className }: {
  option: echarts.EChartsCoreOption
  height?: number
  className?: string
}) {
  const elRef = useRef<HTMLDivElement>(null)
  const instRef = useRef<echarts.ECharts | null>(null)
  const optionRef = useRef(option)
  optionRef.current = option

  useEffect(() => {
    const el = elRef.current
    if (!el) return
    const inst = echarts.init(el)
    instRef.current = inst
    inst.setOption(optionRef.current)
    const ro = new ResizeObserver(() => inst.resize())
    ro.observe(el)
    return () => {
      ro.disconnect()
      inst.dispose()
      instRef.current = null
    }
  }, [])

  useEffect(() => {
    instRef.current?.setOption(option, { notMerge: true })
  }, [option])

  return <div ref={elRef} style={{ height }} className={className} />
}
