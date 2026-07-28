---
kind: frontend_style
name: 前端样式体系：Tailwind CSS + Element Plus 原子化与组件库混合方案
category: frontend_style
scope:
    - '**'
source_files:
    - frontend/tailwind.config.js
    - frontend/postcss.config.js
    - frontend/src/style.css
    - frontend/src/utils/colors.ts
    - frontend/src/layouts/MainLayout.vue
    - frontend/package.json
---

## 1. 系统与方法论
Talos 前端采用 **Tailwind CSS（原子化 CSS）+ Element Plus（Vue 3 UI 组件库）** 的混合样式策略，通过 PostCSS 串联 Tailwind 与 Autoprefixer，由 Vite 统一构建。全局样式入口为 `src/style.css`，使用 `@tailwind base/components/utilities` 指令引入三层样式。

- **Tailwind CSS v3.4**：作为主要布局与工具类来源，启用 `corePlugins.preflight: false` 以避免与 Element Plus 的基础样式冲突。
- **Element Plus v2.7**：提供表格、表单、对话框、消息等业务组件，图标来自 `@element-plus/icons-vue`。
- **PostCSS + Autoprefixer**：在 `postcss.config.js` 中按顺序加载 tailwindcss → autoprefixer，确保跨浏览器兼容。
- **Vite 构建**：`vite.config.ts` 配合 `@vitejs/plugin-vue` 处理 `.vue` 单文件组件中的 `<style>` 块。

## 2. 关键文件与包
- `frontend/tailwind.config.js`：Tailwind 配置，仅扩展 content 路径与关闭 preflight。
- `frontend/postcss.config.js`：PostCSS 插件链（tailwindcss → autoprefixer）。
- `frontend/src/style.css`：全局样式入口，定义基础字体、背景色及富文本/TipTap 编辑器样式。
- `frontend/src/utils/colors.ts`：**全站唯一色源**，集中定义漏洞等级与状态的颜色映射，禁止视图内散落硬编码。
- `frontend/package.json`：声明 element-plus、tailwindcss、autoprefixer、echarts、pinia、vue-router 等依赖。

## 3. 架构与约定
- **布局层**：`src/layouts/MainLayout.vue` 使用 Element Plus 的 `el-container/el-aside/el-header/el-main` 搭建后台管理框架，侧边栏固定 220px、深色背景 `#001529`，顶部 Header 白色带阴影。
- **页面层**：各 `views/*.vue` 通过 vue-router 挂载，页面内部以 Tailwind 原子类为主，辅以少量自定义 CSS（如富文本 `.rich-content`、编辑器 `.tiptap`）。
- **组件层**：`components/` 下复用组件（如 `AssetFormDialog.vue`、`RichEditor.vue`）遵循 Vue SFC 规范，样式写在 `<style scoped>` 中。
- **主题色板**：`utils/colors.ts` 暴露 `LEVEL_COLORS`、`STATUS_COLORS` 及其中文索引版本，并提供 `levelColor()`、`statusColor()` 辅助函数，所有视图必须通过这些导出获取颜色，保证视觉一致性。
- **富文本样式**：基于 TipTap（`@tiptap/vue-3` + starter-kit），在 `style.css` 中统一 `.rich-content` 的图片、表格、代码块、引用块样式，编辑区使用 `.tiptap` 类。

## 4. 约定与约束
- **禁止散落硬编码颜色**：`colors.ts` 注释明确要求“全站统一色板（唯一色源，勿在视图内散落硬编码）”，所有等级/状态颜色必须通过该模块导出获取。
- **Tailwind 与 Element Plus 共存**：通过关闭 `preflight` 避免重置冲突，组件样式优先使用 Element Plus 提供的 class，布局与间距使用 Tailwind 原子类。
- **全局样式集中管理**：字体、背景、富文本、编辑器等跨页面复用的样式统一放在 `src/style.css`，不在组件内重复定义。
- **响应式策略**：未使用媒体查询断点，依赖 Tailwind 的响应式前缀（如 `sm:`、`md:`）与 Flex/Grid 布局实现自适应。
- **图标来源单一**：全部使用 `@element-plus/icons-vue` 的 SVG 图标组件，不引入第三方图标字体或图片图标。
