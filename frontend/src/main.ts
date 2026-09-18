import { createApp, type Component } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as Icons from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './style.css'

import App from './App.vue'
import router from './router'
import { useThemeStore } from './stores/theme'
import { registerChartThemes } from './utils/chartTheme'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })
for (const [name, comp] of Object.entries(Icons)) {
  app.component(name, comp as Component)
}

// 主题初始化：应用持久化的明 / 暗设置，注册 ECharts 双主题
useThemeStore(pinia).init()
registerChartThemes()

// 全局兜底：渲染 / setup 阶段的异常会留下空白或残缺界面，统一落到 500 错误页；
// 事件回调 / 侦听器等阶段仅保留控制台日志（保持原有交互与提示，避免误清屏）。
app.config.errorHandler = (err, _instance, info) => {
  console.error('[talos] 组件异常：', info, err)
  if (info === 'render function' || info === 'setup function') {
    void router.replace({ name: 'error', params: { code: '500' } }).catch(() => undefined)
  }
}

// 懒加载分包失败（多为新版本发布后浏览器仍持有旧 chunk）：先刷新一次拿到最新入口，再次失败才进 500 页
const CHUNK_RELOAD_KEY = 'tl_chunk_reload'
router.onError((error, to) => {
  const message = String((error as Error)?.message ?? error ?? '')
  if (/dynamically imported module|Importing a module script failed|Loading chunk|Failed to fetch dynamically/i.test(message)) {
    if (sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
      sessionStorage.removeItem(CHUNK_RELOAD_KEY)
      void router.replace({ name: 'error', params: { code: '500' } }).catch(() => undefined)
    } else {
      sessionStorage.setItem(CHUNK_RELOAD_KEY, '1')
      window.location.reload()
    }
    return
  }
  if (to?.name !== 'error') {
    void router.replace({ name: 'error', params: { code: '500' } }).catch(() => undefined)
  }
})

app.mount('#app')
