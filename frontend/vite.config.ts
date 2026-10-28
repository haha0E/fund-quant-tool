import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // dev 的依赖扫描不读 tsconfig paths，别名必须在这里显式声明
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // echarts/zrender 单独成 chunk：业务代码迭代重新 build 后该 chunk hash 不变，
        // 配合后端 assets/ 的 immutable 缓存头，手机端日常访问无需重下图表库
        manualChunks(id: string) {
          if (id.includes('echarts') || id.includes('zrender')) return 'echarts'
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期把 /api 转发给 FastAPI（8000），前端代码里统一用相对路径
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
