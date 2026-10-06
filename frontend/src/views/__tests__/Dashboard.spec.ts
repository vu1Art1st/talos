// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

// 收集每次 setOption 的配置：部门横轴标签「隔列隐藏」是回归点，只能从下发配置上断言。
// echarts 在 jsdom 下没有 canvas 上下文（setOption/dispose 会因空上下文抛 TypeError），故以桩替换；
// 真实渲染（标签截断、不重叠）由浏览器冒烟覆盖。
const { chartOptions } = vi.hoisted(() => ({ chartOptions: [] as Array<Record<string, unknown>> }))

vi.mock('echarts', () => ({
  init: () => ({
    setOption: (option: Record<string, unknown>) => { chartOptions.push(option) },
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
  registerTheme: vi.fn(),
  // 趋势图面积渐变：只需能构造成功
  graphic: { LinearGradient: class {} },
}))

// stores/auth.ts 经 router/index.ts 间接依赖 createRouter/createWebHistory，
// 故用 importOriginal 保留真实导出、仅覆盖 hook。
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ query: {}, path: '/dashboard', fullPath: '/dashboard' }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  }
})

vi.mock('../../api/client', () => clientMockFactory())

import Dashboard from '../Dashboard.vue'

// 长短悬殊的部门名（最长 14 字）是本次缺陷的触发条件
const DEPARTMENTS = ['数智化部', 'AI业务部', '产品事业部', '中移海算科技（雄安）有限公司']

// vitest 的 jsdom 环境未注入 localStorage（Node 内建实现不可用），用内存版替身
const storage = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storage.get(k) ?? null,
  setItem: (k: string, v: string) => storage.set(k, v),
  removeItem: (k: string) => storage.delete(k),
})

function statsFixture() {
  return {
    total_vulns: 20, total_assets: 3, open_vulns: 5, fix_rate: 75,
    by_status: [], by_level: [], by_type: [], trend: [],
    sla: { by_department: [] },
    ops: {},
    by_department: DEPARTMENTS.map((department, i) => ({
      department, plans: 4 - i, vulns: 10, high: 2, fixed: 8, open: 2,
      fix_rate: 80, mandays: 1.5,
    })),
  }
}

interface DeptAxis {
  data: string[]
  axisLabel: { interval: number; width: number; overflow?: string; hideOverlap?: boolean }
}

/** 应用字典元数据最小载荷：`applyDictMeta` 逐键读取，缺 `colors` 会在挂载期抛错 */
function metaFixture() {
  return {
    vul_type: {}, vul_level: {}, vul_status: {}, vul_source: {}, vul_layer: {},
    asset_sec_level: {}, asset_status: {}, system_type: [], url_tag: {},
    testing_plan_status: {}, import_batch_status: {},
    import_record_status: {}, export_job_status: {}, permissions: [],
    colors: {
      vul_level: {}, vul_status: {}, vul_type: {}, testing_plan_status: {},
      asset_status: {}, url_tag: {}, nonpen_item: {},
      import_batch_status: {}, import_record_status: {}, export_job_status: {},
    },
    nonpen: { items: [], status: {}, actions: {}, action_names: {} },
  }
}

/** 取「部门安全概况」图表的横轴配置（按横轴取值为部门名识别，避免依赖图表渲染顺序） */
function deptAxis(): DeptAxis {
  const option = chartOptions.find((o) => {
    const x = o.xAxis as { type?: string; data?: unknown } | undefined
    return x?.type === 'category' && Array.isArray(x.data) && x.data.includes('AI业务部')
  })
  if (!option) throw new Error('未渲染「各部门安全概况」图表')
  return option.xAxis as DeptAxis
}

describe('Dashboard 安全态势看板', () => {
  beforeEach(() => {
    chartOptions.length = 0
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/dashboard/stats') return { data: statsFixture() }
      if (url === '/dashboard/views') return { data: [] }
      if (url === '/meta') return { data: metaFixture() }
      return { data: [] }
    })
  })

  it('部门横轴标签全量显示：关闭 auto 间隔并按列宽截断', async () => {
    const wrapper = mount(Dashboard, { global: { plugins: [ElementPlus, createPinia()] } })
    await flushPromises()

    const axis = deptAxis()
    expect(axis.data).toEqual(DEPARTMENTS)
    // interval: 0 —— 默认 'auto' 会按最长部门名把间隔提到 1，导致半数部门标签为空（回归点）
    expect(axis.axisLabel.interval).toBe(0)
    expect(axis.axisLabel.width).toBeGreaterThanOrEqual(56)
    expect(axis.axisLabel.overflow).toBe('truncate')
    expect(wrapper.text()).toContain('中移海算科技（雄安）有限公司')
  })
})
