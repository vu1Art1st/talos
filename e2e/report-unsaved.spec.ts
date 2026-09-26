/**
 * 报告编辑防丢稿 E2E（ROADMAP P0-5）：三条链路。
 *
 * 为什么必须放浏览器里验：这三条链的判据全部落在「浏览器事件的时序」上——
 * 3 秒防抖计时器、路由离开钩子、`beforeunload`、两个标签页之间的 revision 冲突；
 * pytest（无浏览器）与 vitest（全量 mock axios/路由）都覆盖不到。
 *
 * 约定与 golden-path.spec.ts 一致：`data-test` 定位、断言控制台无 error、不截图不断言 canvas。
 */
import { expect, test, type Page } from '@playwright/test'

const ADMIN = { username: 'admin', password: 'admin123' }
/** 本次运行唯一后缀：避免与 E2E 库历史数据混淆，也让失败现场可追溯 */
const RUN_ID = Date.now().toString(36)

let consoleErrors: string[] = []

/**
 * 本文件会**故意**触发 4xx/5xx（保存失败与 revision 冲突），而 Chrome 对任何非 2xx 响应都会
 * 在控制台留一条 `Failed to load resource` 的 error 级消息 —— 这是被测行为本身，不是缺陷。
 * 故按用例声明「预期内的 HTTP 状态日志」，其余 error（含 pageerror）仍一律失败。
 */
let allowedConsole: RegExp[] = []

test.beforeEach(async ({ page }) => {
  consoleErrors = []
  allowedConsole = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`))
})

test.afterEach(async () => {
  const unexpected = consoleErrors.filter((text) => !allowedConsole.some((re) => re.test(text)))
  expect(unexpected, `控制台出现 error：\n${unexpected.join('\n')}`).toEqual([])
})

async function login(page: Page): Promise<void> {
  await page.goto('/login')
  await page.getByTestId('login-username').fill(ADMIN.username)
  await page.getByTestId('login-password').fill(ADMIN.password)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/dashboard/)
}

/** 从报告中心进入第一条报告，返回其编辑页 URL。 */
async function openFirstReport(page: Page): Promise<string> {
  await page.goto('/reports')
  const firstRow = page.locator('tbody tr').first()
  await expect(firstRow).toBeVisible()
  await firstRow.getByRole('button', { name: '编辑' }).click()
  await expect(page).toHaveURL(/\/reports\/\d+$/)
  await expect(page.getByTestId('report-title')).toBeVisible()
  return page.url()
}

test('编辑后 3 秒内离开：先补存一次再放行（不弹窗、不丢稿）', async ({ page }) => {
  await login(page)
  const editorUrl = await openFirstReport(page)
  const original = await page.getByTestId('report-title').inputValue()
  const updated = `${original}-离页${RUN_ID}`

  // 编辑后立刻离开（远早于 3 秒防抖自动保存）
  await page.getByTestId('report-title').fill(updated)
  await expect(page.getByTestId('report-save-state')).toContainText('有未保存修改')
  await page.getByTestId('report-back').click()

  // 保存成功即放行：不打扰用户（仅保存失败时才弹三选一）
  await expect(page).toHaveURL(/\/reports$/)
  await expect(page.locator('.el-message-box')).toHaveCount(0)

  // 重新打开同一报告：标题已落库（证明离开前确实补存，而不是静默丢弃）
  await page.goto(editorUrl)
  await expect(page.getByTestId('report-title')).toHaveValue(updated)
})

test('离页且保存失败：三选一提示，可留在当前页或放弃修改', async ({ page }) => {
  allowedConsole = [/status of 500/] // 注入的服务端异常
  await login(page)
  const editorUrl = await openFirstReport(page)
  const original = await page.getByTestId('report-title').inputValue()
  const updated = `${original}-离页失败${RUN_ID}`

  // 让保存始终失败
  await page.route('**/api/v1/reports/*', async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '模拟服务端异常' }),
      })
      return
    }
    await route.continue()
  })

  await page.getByTestId('report-title').fill(updated)
  await page.getByTestId('report-back').click()

  const dialog = page.locator('.el-message-box')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('未保存的修改')

  // 关掉弹窗（X）= 留在当前页：导航被取消，本地输入保留
  await dialog.locator('.el-message-box__headerbtn').click()
  await expect(page).toHaveURL(editorUrl)
  await expect(page.getByTestId('report-title')).toHaveValue(updated)

  // 再次离开 → 选择「放弃修改」→ 放行
  await page.getByTestId('report-back').click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '放弃修改' }).click()
  await expect(page).toHaveURL(/\/reports$/)
})

test('保存失败后重试：留在编辑页并可重试成功（不跳错误页、不丢输入）', async ({ page }) => {
  allowedConsole = [/status of 500/] // 注入的服务端异常
  await login(page)
  const editorUrl = await openFirstReport(page)
  const original = await page.getByTestId('report-title').inputValue()
  const updated = `${original}-重试${RUN_ID}`

  // 注入保存失败（5xx）：必须留在编辑页（skipErrorPage），仅轻提示 + 失败态
  let failSaves = true
  await page.route('**/api/v1/reports/*', async (route) => {
    if (failSaves && route.request().method() === 'PUT') {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '模拟服务端异常' }),
      })
      return
    }
    await route.continue()
  })

  await page.getByTestId('report-title').fill(updated)
  // 3 秒防抖自动保存失败 → 状态可见、且未被错误页清屏
  await expect(page.getByTestId('report-save-state')).toContainText('保存失败', { timeout: 10000 })
  await expect(page).toHaveURL(editorUrl)
  await expect(page.getByTestId('report-title')).toHaveValue(updated) // 本地输入保留

  // 恢复后点「保存报告」重试 → 成功
  failSaves = false
  await page.getByTestId('report-save').click()
  await expect(page.getByTestId('report-save-state')).toContainText('已保存')
})

test('409 冲突：不静默覆盖，提示后可继续编辑或加载最新', async ({ page, context }) => {
  allowedConsole = [/status of 409/] // 被测行为：revision 过期后的冲突响应
  await login(page)
  const editorUrl = await openFirstReport(page)
  const original = await page.getByTestId('report-title').inputValue()

  // 第二个标签页打开同一报告并把 revision 推进一格，使第一个页面的 revision 过期
  const other = await context.newPage()
  await other.goto(editorUrl)
  await expect(other.getByTestId('report-title')).toBeVisible()
  const otherTitle = `${original}-他人修改${RUN_ID}`
  await other.getByTestId('report-title').fill(otherTitle)
  await other.getByTestId('report-save').click()
  await expect(other.getByTestId('report-save-state')).toContainText('已保存')
  await other.close()

  // 第一个页面（revision 已过期）保存 → 409 → 冲突弹窗
  const localTitle = `${original}-本地${RUN_ID}`
  await page.getByTestId('report-title').fill(localTitle)
  await page.getByTestId('report-save').click()

  const conflict = page.locator('.el-message-box')
  await expect(conflict).toBeVisible()
  await expect(conflict).toContainText('版本冲突')
  // 选择「继续编辑」：保留本地内容（不得静默覆盖为他人版本）
  await conflict.getByRole('button', { name: '继续编辑' }).click()
  await expect(page.getByTestId('report-title')).toHaveValue(localTitle)
  await expect(page.getByTestId('report-save-state')).toContainText('版本冲突')

  // 再保存一次仍冲突 → 选择「加载最新」后回落到服务端内容
  await page.getByTestId('report-save').click()
  await expect(conflict).toBeVisible()
  await conflict.getByRole('button', { name: '加载最新' }).click()
  await expect(page.getByTestId('report-title')).toHaveValue(otherTitle)
  await expect(page.getByTestId('report-save-state')).toContainText('已保存')
})
