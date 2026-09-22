/**
 * 黄金链路 E2E（Playwright + 系统 Chrome）。
 *
 * 只覆盖「后端 pytest 与前端 vitest 都证明不了」的那一层：浏览器里真能点通、真能提交、真能渲染。
 * 后端测试走 ASGI 进程内、前端测试全量 mock axios，二者都无法发现「前端把参数拼错 / 字段漏声明 /
 * 接口对不上」。这里不做页面铺量（12 页广度仍由分级人工冒烟负责），只守 3 条链：
 *   ① 登录（所有页面的前置）
 *   ② 新建漏洞 + 影响URL 批量粘贴（前端交互最复杂、且历史上出过归一化事故的一条写链路）
 *   ③ 报告编辑器渲染（最重的只读页面，覆盖富文本/图表/表格）
 *
 * 稳定性约定（照抄即不会踩坑）：
 * - 一律用 `data-test` 定位（本项目文案高频变更，文本选择器会随改名而碎）；
 * - **不做截图基线、不断言 canvas**（项目有 21 处 ECharts，canvas 渲染不稳定）；
 * - 每条用例开头/结尾断言**控制台无 error**（与人工冒烟同一判据，见 AGENTS.md 验收口径）。
 */
import { expect, test, type Page } from '@playwright/test'

/** 种子数据账号（`python -m scripts.seed_dev_data --reset` 固定创建） */
const ADMIN = { username: 'admin', password: 'admin123' }
/** 本次运行的唯一后缀：避免与 E2E 库中历史数据重名，也让失败现场可追溯 */
const RUN_ID = Date.now().toString(36)

let consoleErrors: string[] = []

test.beforeEach(async ({ page }) => {
  consoleErrors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))
})

test.afterEach(async () => {
  expect(consoleErrors, `控制台出现 error：\n${consoleErrors.join('\n')}`).toEqual([])
})

async function login(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByTestId('login-username').fill(ADMIN.username)
  await page.getByTestId('login-password').fill(ADMIN.password)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/dashboard/)
}

test('登录后进入安全态势（控制台无错误）', async ({ page }) => {
  await login(page)
  await expect(page.getByRole('heading', { name: '安全态势' })).toBeVisible()
})

test('新建漏洞：影响URL 批量粘贴自动切分并提交成功', async ({ page }) => {
  await login(page)
  await page.goto('/vulns/new')

  // 测试目标必填；资产下拉在挂载时已预加载前 50 个资产，直接取第一项（不依赖种子资产名字）
  await page.getByTestId('vuln-assets').click()
  await page.locator('.el-select-dropdown__item:visible').first().click()
  await page.keyboard.press('Escape')

  const title = `E2E批量粘贴-${RUN_ID}`
  await page.getByTestId('vuln-title').fill(title)

  // 选中资产后，编辑器会自动带出该资产的 URL（产品行为）—— 先清空这一行，
  // 使断言与「所选资产是否录了 URL」解耦（否则行数会随种子数据/下拉顺序变化）。
  const firstInput = page.getByTestId('affected-url-input').first()
  await firstInput.click()
  await page.keyboard.press('ControlOrMeta+a')
  await page.keyboard.press('Delete')

  // 单行 input 会丢弃换行，故编辑器必须在 paste 事件里读原文 —— 这里模拟真实粘贴（含 1 条重复项）
  const pasted = [
    'http://e2e-a.example.com/login?id=1',
    'https://e2e-b.example.com/api/v1/items',
    'http://e2e-a.example.com/login?id=1',
    '10.9.9.9:8080/admin',
  ]
  const pasteInto = async (target: ReturnType<Page['getByTestId']>) => {
    await target.evaluate((el, text) => {
      const data = new DataTransfer()
      data.setData('text/plain', text)
      el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }))
    }, pasted.join('\n'))
  }
  await pasteInto(firstInput)

  // 口径（`utils/urls.parseAffectedUrl` = 切分 + cleanUrls 去空/去重保序）：粘贴文本内部的重复
  // 在「识别」阶段即被去掉，故 4 行里有 1 条重复 → 提示「已识别 3 条」，且**不**出现「已去重」后缀
  await expect(page.getByTestId('affected-url-hint')).toContainText('已识别 3 条')
  await expect(page.getByTestId('affected-url-input')).toHaveCount(3)

  // 再粘一次同样内容：这次全部与已有行重复 → 触发「已去重」提示（覆盖另一分支），行数不变
  await pasteInto(page.getByTestId('affected-url-input').first())
  await expect(page.getByTestId('affected-url-hint')).toContainText('已去重 3 条')
  await expect(page.getByTestId('affected-url-input')).toHaveCount(3)

  await page.getByTestId('vuln-save').click()
  await expect(page).toHaveURL(/\/vulns\/\d+$/)
  await expect(page.locator('body')).toContainText(title)
  await expect(page.locator('body')).toContainText('e2e-a.example.com')
})

test('报告中心：打开报告编辑器并完成渲染', async ({ page }) => {
  await login(page)
  await page.goto('/reports')

  const firstRow = page.locator('tbody tr').first()
  await expect(firstRow).toBeVisible()
  await firstRow.getByRole('button', { name: '编辑' }).click()

  await expect(page).toHaveURL(/\/reports\/\d+$/)
  // 编辑器骨架：富文本区与章节导航均渲染（不深入断言正文，避免耦合具体报告内容）
  await expect(page.locator('.ProseMirror').first()).toBeVisible()
})
