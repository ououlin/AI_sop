import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发期代理 WebSocket 与 API 到后端 8000
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
