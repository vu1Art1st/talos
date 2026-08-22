// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'

// mock 路由：报告 ID 来自路由参数
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

// mock 导出任务 composable：报告编辑器对它仅有提交/轮询调用，冒烟无需真实行为
vi.mock('../../composables/useExportJobs', () => ({
  useExportJobs: () => ({
    fetchJobs: vi.fn(async () => []),
    submitExport: vi.fn(async () => true),
    downloadJob: vi.fn(),
    removeExportJob: vi.fn(),
  }),
}))

// mock axios client：报告详情返回最小可渲染结构，其余接口返回空数据
const getMock = vi.fn()
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import ReportEditor from '../ReportEditor.vue'

function reportFixture() {
  return {
    id: 1, title: '商城系统渗透测试报告', project_name: '商城系统', customer: '',
    author: '', test_start: '', test_end: '', target_ip: '', status: 'draft',
    revision: 0, version: 1, actual_mandays: 0, testing_plan_id: null,
    sections: [{ id: 1, order: 0, title: '测试结论', content_html: '<p>结论</p>', vul_id: null }],
  }
}

function metaFixture() {
  return {
    vul_type: {}, vul_level: {}, vul_status: {}, vul_source: {}, vul_layer: {},
    asset_sec_level: {}, asset_status: {}, system_type: [], url_tag: {},
    testing_plan_status: {}, report_status: {}, import_batch_status: {},
    import_record_status: {}, export_job_status: {}, permissions: [],
    colors: {
      vul_level: {}, vul_status: {}, vul_type: {}, testing_plan_status: {},
      report_status: {}, asset_status: {}, url_tag: {}, nonpen_item: {},
      import_batch_status: {}, import_record_status: {}, export_job_status: {},
    },
    nonpen: { items: [], status: {}, actions: {}, action_names: {} },
  }
}

describe('ReportEditor 视图', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/reports/1') return { data: reportFixture() }
      if (url === '/meta') return { data: metaFixture() }
      return { data: [] }
    })
  })

  afterEach(() => {
    // 视图的导出轮询 setInterval 需随用例清理，避免泄漏到其它用例
    vi.clearAllTimers()
  })

  it('挂载不抛错，首屏加载报告详情并渲染章节标题', async () => {
    const wrapper = mount(ReportEditor, {
      global: {
        plugins: [ElementPlus, createPinia()],
        // 富文本/漏洞录入等重子组件替换为占位，冒烟只验证编辑器自身
        stubs: {
          RichEditor: { template: '<div class="rich-stub" />' },
          VulnFormPanel: { template: '<div class="vuln-stub" />' },
          VulnRetestPanel: { template: '<div class="retest-stub" />' },
          PdfPreviewDialog: { template: '<div class="pdf-stub" />' },
        },
      },
    })
    await flushPromises()
    expect(getMock).toHaveBeenCalledWith('/reports/1')
    expect(wrapper.text()).toContain('测试结论')
    wrapper.unmount()
  })
})
