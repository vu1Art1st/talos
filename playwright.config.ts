/**
 * Talos 端到端测试配置（Playwright）。
 *
 * 定位：**只跑 2~3 条黄金链路**，用来补「前后端真实联调」这一层 —— 后端 pytest 走 ASGI、
 * 前端 vitest 全 mock axios，两者都证明不了浏览器里真能点通。12 页人工冒烟仍保留（分级执行，
 * 见 AGENTS.md 验收口径），本套件不试图取代它。
 *
 * 关键取舍：
 * - `channel: 'chrome'` —— 直接用**系统 Chrome**，不下载 Playwright 自带 Chromium（省 ~195 MB）；
 * - `workers: 1` + `fullyParallel: false` —— E2E 写的是同一个 `vulnplatform_e2e` 库，串行最稳，
 *   也避免"并发写同一份数据"这类自己造出来的 flakiness；
 * - `retries: 1` + `trace: 'on-first-retry'` —— 本地偶发抖动留证据，但不掩盖失败；
 * - **禁止截图基线 / canvas 断言**：项目有 21 处 ECharts（canvas 渲染不稳定），只断 DOM 与 console。
 *
 * 由 `scripts/e2e.ps1` / `e2e.sh` 编排（迁移+种子+起 api+起前端+跑本配置），也可在栈已手动起好的
 * 情况下直接 `pnpm e2e`（需自行设 E2E_BASE_URL 指向前端地址）。
 */
import { defineConfig } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:27017'

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  forbidOnly: false,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report' }]],
  outputDir: 'e2e-results',
  use: {
    baseURL: BASE_URL,
    channel: 'chrome',
    // 本仓库统一用 `data-test`（非 Playwright 默认的 data-testid）
    testIdAttribute: 'data-test',
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },
})
