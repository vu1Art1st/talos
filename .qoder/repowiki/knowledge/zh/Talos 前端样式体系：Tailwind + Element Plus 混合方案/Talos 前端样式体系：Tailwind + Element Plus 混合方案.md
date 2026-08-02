---
kind: frontend_style
name: Talos 前端样式体系：Tailwind + Element Plus 混合方案
category: frontend_style
scope:
    - '**'
source_files:
    - frontend/tailwind.config.js
    - frontend/postcss.config.js
    - frontend/src/style.css
    - frontend/src/utils/colors.ts
    - frontend/src/layouts/MainLayout.vue
    - frontend/src/components/RichEditor.vue
---

## 1. 使用的系统与工具
- CSS 框架：Tailwind CSS 3.x（原子化 utility-first 风格）
- UI 组件库：Element Plus 2.x（Vue 3 桌面端组件库）
- 构建与样式处理链：Vite 5 + PostCSS（autoprefixer）+ Tailwind
- 富文本编辑器：TipTap 2（@tiptap/vue-3 + starter-kit + image/link/table 扩展）
- 图表：ECharts 5
- 状态管理：Pinia（样式相关状态集中在 src/utils/colors.ts）

## 2. 核心文件与位置
- frontend/tailwind.config.js — Tailwind 配置，关闭 preflight 避免与 Element Plus 冲突
- frontend/postcss.config.js — PostCSS 插件链（tailwindcss → autoprefixer）
- frontend/src/style.css — 全局样式入口，注入 Tailwind base/components/utilities，定义全局字体、背景色及富文本统一样式
- frontend/src/utils/colors.ts — 全站唯一色板来源（漏洞等级/状态颜色），禁止视图内散落硬编码
- frontend/src/layouts/MainLayout.vue — 主布局，使用 Element Plus Container + Tailwind 组合布局
- frontend/src/components/RichEditor.vue — TipTap 编辑器封装，大量使用 Tailwind 原子类

## 3. 架构与设计约定
- 混合样式策略：页面级布局与通用 UI 通过 Element Plus 组件提供一致性；业务细节样式通过 Tailwind 原子类快速实现。两者通过关闭 Tailwind preflight 避免重置冲突。
- 设计令牌集中化：所有语义化颜色（严重/高危/中危/低危/安全、未修复/修复中/已修复/已忽略等）统一在 src/utils/colors.ts 暴露，组件通过函数 levelColor() / statusColor() 获取，禁止在模板中直接写死色值。
- 富文本样式隔离：.rich-content 与 .tiptap 两类选择器在 style.css 中统一定义，确保编辑器渲染内容与编辑区外观一致。
- 布局结构：采用 Element Plus 的 el-container + el-aside + el-header + el-main 经典后台布局，侧边栏固定宽度 220px、深色背景 #001529，顶部 header 白色带阴影。
- 响应式策略：未引入移动端适配框架，整体为桌面端后台管理系统风格，依赖浏览器默认视口行为。

## 4. 约定与约束
- Tailwind 内容扫描范围：仅扫描 ./index.html 与 ./src/**/*.{vue,ts}，避免打包无关样式。
- 禁止预置样式重置：corePlugins.preflight: false，由 Element Plus 承担基础重置。
- 颜色使用规范：colors.ts 注释明确“唯一色源，勿在视图内散落硬编码”，违反该约定的代码会被视为样式不一致。
- 富文本内容样式：.rich-content 下图片最大宽度 100%、圆角 4px、边框 #ebeef5；表格合并边框、单元格 #dcdfe6 边框；代码块深色主题 #282c34；引用左侧蓝色边框 #409eff 配浅蓝背景 #ecf5ff。
- 编辑器占位符：通过 ::before + attr(data-placeholder) 实现，指针事件禁用避免干扰输入。
- 全局字体栈：'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif，优先苹方/微软雅黑以保障中文显示。
- 全局背景色：#f5f7fa（浅灰），与 Element Plus 默认卡片白底形成层次。

## 5. 未发现的样式机制
- 未发现 SCSS/Less/Stylus 预处理文件，全部使用原生 CSS + Tailwind。
- 未发现 CSS Modules、CSS-in-JS（如 styled-components）、或自定义主题变量覆盖机制。
- 未发现暗色模式切换逻辑，当前为固定浅色主题。