// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const searchMock = vi.fn()
const detailMock = vi.fn()
vi.mock('../../api/knowledge', () => ({
  searchKnowledge: (...args: unknown[]) => searchMock(...args),
  getKnowledgeEntry: (...args: unknown[]) => detailMock(...args),
}))

// 屏蔽 auth store（其导入链会拉起 router/pinia）：仅需 fetchMeta 返回可用字典
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    meta: null,
    fetchMeta: vi.fn().mockResolvedValue({
      vul_type: { 10: 'SQL注入漏洞', 40: '权限绕过' },
      vul_level: { 10: '严重', 20: '高危', 30: '中危' },
    }),
  }),
}))

import TemplatePickerDialog from '../TemplatePickerDialog.vue'

const RESULT_ITEMS = [
  {
    id: 1,
    vulnerability_name: '搜索用例-SQL注入（CVE-2099-1111）',
    vul_type: 10,
    vul_type_name: 'SQL注入漏洞',
    severity_level: 10,
    summary: '拼接 SQL 语句导致注入',
    username: '张三',
    update_time: '2026-09-10T10:00:00',
    matched_field: 'name',
  },
]

const mountDialog = (vulType: number | null) =>
  mount(TemplatePickerDialog, {
    props: { modelValue: false, vulType },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })

async function open(wrapper: ReturnType<typeof mountDialog>) {
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  await flushPromises()
}

const lastParams = () => searchMock.mock.calls.at(-1)?.[0] as Record<string, unknown>

const radioInputs = () => Array.from(document.body.querySelectorAll<HTMLInputElement>('.el-radio-button input'))

describe('TemplatePickerDialog 跨模板搜索弹窗', () => {
  beforeEach(() => {
    searchMock.mockReset()
    detailMock.mockReset()
    searchMock.mockResolvedValue({ data: { total: RESULT_ITEMS.length, items: RESULT_ITEMS } })
    detailMock.mockResolvedValue({ data: { ...RESULT_ITEMS[0], description_html: '<p>完整正文</p>' } })
    document.body.innerHTML = ''
  })

  // 保留原有模板内搜索：默认作用域必须是当前漏洞类型
  it('默认作用域为当前漏洞类型，请求带该类型且结果展示所属模板路径', async () => {
    const wrapper = mountDialog(10)
    await open(wrapper)

    expect(searchMock).toHaveBeenCalledTimes(1)
    expect(lastParams().vul_type).toEqual([10])
    expect(document.body.textContent).toContain('当前类型：SQL注入漏洞')
    // 结果标注危害等级、所属模板（漏洞类型）与派生路径、维护人
    expect(document.body.textContent).toContain('严重')
    expect(document.body.textContent).toContain('漏洞模板库 / SQL注入漏洞 / 搜索用例-SQL注入（CVE-2099-1111）')
    expect(document.body.textContent).toContain('张三')
    wrapper.unmount()
  })

  it('切换到「全部模板」后按全局作用域重新检索（不再限定漏洞类型）', async () => {
    const wrapper = mountDialog(10)
    await open(wrapper)
    expect(lastParams().vul_type).toEqual([10])

    radioInputs()[1].click() // 第 2 个按钮＝全部模板
    await flushPromises()

    expect(lastParams().vul_type).toEqual([])
    wrapper.unmount()
  })

  it('当前类型无结果时给出「在全部模板中搜索」引导并可一键切全局', async () => {
    searchMock.mockResolvedValue({ data: { total: 0, items: [] } })
    const wrapper = mountDialog(10)
    await open(wrapper)

    const guide = Array.from(document.body.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('在全部模板中搜索'),
    )
    expect(guide).toBeTruthy()
    expect(document.body.textContent).toContain('该漏洞类型暂无模板')

    guide!.click()
    await flushPromises()
    expect(lastParams().vul_type).toEqual([])
    wrapper.unmount()
  })

  it('选中结果后按 ID 取完整正文并 emit select（不自行关闭，交由宿主确认覆盖）', async () => {
    const wrapper = mountDialog(10)
    await open(wrapper)

    const card = document.body.querySelector<HTMLElement>('[data-idx="0"]')
    expect(card).toBeTruthy()
    card!.click()
    await flushPromises()

    expect(detailMock).toHaveBeenCalledWith(1)
    const selected = wrapper.emitted('select')
    expect(selected).toBeTruthy()
    expect((selected![0][0] as Record<string, unknown>).description_html).toBe('<p>完整正文</p>')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    wrapper.unmount()
  })

  it('未传当前漏洞类型时直接进入「全部模板」作用域', async () => {
    const wrapper = mountDialog(null)
    await open(wrapper)
    expect(lastParams().vul_type).toEqual([])
    wrapper.unmount()
  })
})
