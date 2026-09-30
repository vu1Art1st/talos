// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

const fileViewerMocks = vi.hoisted(() => ({
  printRenderedHtml: vi.fn(),
  destroy: vi.fn(),
}))

vi.mock('../../api/client', () => clientMockFactory())
vi.mock('@file-viewer/vue3', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    FileViewer: defineComponent({
      name: 'FileViewer',
      props: {
        file: { type: File, required: true },
        options: { type: Object, required: true },
      },
      emits: ['load-start', 'load-complete', 'error'],
      setup(props, { expose, emit }) {
        expose({
          printRenderedHtml: fileViewerMocks.printRenderedHtml,
          destroy: fileViewerMocks.destroy,
        })
        return () => h('div', {
          class: 'file-viewer-stub',
          onClick: () => emit('load-complete'),
        }, props.file.name)
      },
    }),
  }
})

import FilePreviewDialog from '../FilePreviewDialog.vue'

const DIALOG_STUB = {
  props: ['modelValue'],
  template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>',
}
const BUTTON_STUB = {
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function mountDialog() {
  setActivePinia(createPinia())
  const wrapper = mount(FilePreviewDialog, {
    global: {
      directives: { loading: () => undefined },
      stubs: {
        'el-dialog': DIALOG_STUB,
        'el-button': BUTTON_STUB,
        'el-empty': {
          props: ['description'],
          template: '<div class="empty-stub">{{ description }}</div>',
        },
        'el-icon': { template: '<span><slot /></span>' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

function componentApi(wrapper: Awaited<ReturnType<typeof mountDialog>>) {
  return wrapper.vm as unknown as { open: (url: string, name?: string) => Promise<void> }
}

beforeEach(() => {
  getMock.mockReset()
  fileViewerMocks.printRenderedHtml.mockReset()
  fileViewerMocks.destroy.mockReset()
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('FilePreviewDialog', () => {
  it('携带鉴权参数拉取 DOCX，补全扩展名后交给 File Viewer', async () => {
    getMock.mockResolvedValueOnce({ data: new Blob(['docx']) })
    const wrapper = await mountDialog()
    await componentApi(wrapper).open('/imports/1/preview', '测试报告')
    await flushPromises()

    expect(getMock).toHaveBeenCalledWith(
      '/imports/1/preview',
      expect.objectContaining({ responseType: 'blob', signal: expect.any(AbortSignal) }),
    )
    expect(wrapper.get('.file-viewer-stub').text()).toBe('测试报告.docx')
  })

  it('加载完成后调用 viewer 打印接口', async () => {
    getMock.mockResolvedValueOnce({ data: new Blob(['docx']) })
    fileViewerMocks.printRenderedHtml.mockResolvedValue(undefined)
    const wrapper = await mountDialog()
    await componentApi(wrapper).open('/reports/exports/1/preview', '报告.docx')
    await flushPromises()

    await wrapper.get('.file-viewer-stub').trigger('click')
    const printButton = wrapper.findAll('button').find((button) => button.text().includes('打印'))
    expect(printButton).toBeTruthy()
    await printButton!.trigger('click')
    expect(fileViewerMocks.printRenderedHtml).toHaveBeenCalledOnce()
  })

  it('拉取失败时保留错误态并退出加载', async () => {
    getMock.mockRejectedValueOnce(new Error('500'))
    const wrapper = await mountDialog()
    await componentApi(wrapper).open('/imports/1/preview', '测试报告.docx')
    await flushPromises()

    expect(wrapper.text()).toContain('预览加载失败')
    expect(wrapper.find('.file-viewer-stub').exists()).toBe(false)
  })

  it('连续打开时取消旧请求，旧响应不得覆盖新文件', async () => {
    const first = deferred<{ data: Blob }>()
    const second = deferred<{ data: Blob }>()
    getMock
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)

    const wrapper = await mountDialog()
    const api = componentApi(wrapper)
    const firstOpen = api.open('/imports/1/preview', '第一份.docx')
    const firstSignal = getMock.mock.calls[0]?.[1]?.signal as AbortSignal
    const secondOpen = api.open('/imports/2/preview', '第二份.docx')
    expect(firstSignal.aborted).toBe(true)

    first.resolve({ data: new Blob(['old']) })
    second.resolve({ data: new Blob(['new']) })
    await Promise.all([firstOpen, secondOpen])
    await flushPromises()

    expect(wrapper.get('.file-viewer-stub').text()).toBe('第二份.docx')
  })
})
