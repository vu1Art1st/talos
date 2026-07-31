import { createApp } from 'vue'
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
  app.component(name, comp as any)
}

// 主题初始化：应用持久化的明 / 暗设置，注册 ECharts 双主题
useThemeStore(pinia).init()
registerChartThemes()

app.mount('#app')
