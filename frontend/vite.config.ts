import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 允许局域网 IP 和穿透隧道域名访问（分享用）
    allowedHosts: ['.trycloudflare.com', '.cpolar.top'],
  },
  preview: {
    // 生产预览/公网分享：/api 同源代理到本机后端，单隧道即可，前端无需知道 API 隧道地址
    allowedHosts: ['.trycloudflare.com', '.cpolar.top'],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
