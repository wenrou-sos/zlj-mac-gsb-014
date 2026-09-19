import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式下把 /api 代理到 FastAPI；生产由 nginx 反代
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
