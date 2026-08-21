import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 端口支持环境变量覆盖（dev.sh / dev.ps1 会注入），默认前端 27014、后端 27015
const frontendPort = Number(process.env.VP_FRONTEND_PORT || 27014)
const backendPort = Number(process.env.VP_BACKEND_PORT || 27015)

export default defineConfig({
  plugins: [vue()],
  // 单测（vitest）：纯逻辑测试用 node 环境即可，无需 jsdom
  test: {
    environment: 'node',
    include: ['src/**/__tests__/*.spec.ts'],
  },
  server: {
    // 绑定 0.0.0.0 以支持通过 VPS_IP:PORT 从外部访问（仅绑定 localhost 时外部无法连接）
    host: '0.0.0.0',
    port: frontendPort,
    strictPort: true,
    proxy: {
      '/api': { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true },
      '/storage': { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true },
    },
  },
})
