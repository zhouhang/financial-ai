import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: ['dev.tallyai.cn'],
    headers: {
      'Cache-Control': 'no-store, max-age=0',
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        ws: true,
      },
    },
  },
})
