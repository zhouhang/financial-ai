import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// /api 反向代理:剥掉 /api 前缀转发到 data-agent(8100)。
// dev(server)和生产预览(preview)都要用,所以抽出来共用。
const apiProxy = {
  '/api': {
    target: 'http://localhost:8100',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ''),
    ws: true,
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 开发服务器:HMR 热更新,no-store 防陈旧代码。加载慢(几百个未打包模块),只用于本地开发。
  server: {
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: ['dev.tallyai.cn'],
    headers: {
      'Cache-Control': 'no-store, max-age=0',
    },
    proxy: apiProxy,
  },
  // 生产预览:`npm run build` 产出的 dist 静态包 + `vite preview`。
  // dev.tallyai.cn 临时生产走这个 —— 少数带 hash 的 bundle,可被浏览器/Cloudflare 缓存,
  // 加载快且稳定。/api 代理这里必须再配一份(server.proxy 不对 preview 生效)。
  preview: {
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: ['dev.tallyai.cn'],
    proxy: apiProxy,
  },
})
