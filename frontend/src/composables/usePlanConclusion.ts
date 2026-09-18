import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import client from '../api/client'
import type { PlanConclusion, QueryParams } from '../types'
import { saveBlob } from '../utils/download'

/**
 * 工单列表「结论输出」面板（审计 E-2 从 views/TestingPlanList.vue 抽出）。
 *
 * 职责：按当前筛选条件取结论聚合数据、复制结论文本、导出整改情况附件。
 *
 * @param getFilterParams 取当前筛选参数（与列表/统计共用同一份口径，由调用方从 `filterParams()` 传入）
 */
export function usePlanConclusion(getFilterParams: () => QueryParams) {
  // el-collapse 的展开项（仅 UI 展示态，留在本 composable 与面板同生命周期）
  const conclusionPanel = ref<string[]>([])
  const conclusion = ref<PlanConclusion>({})
  const conclusionLoading = ref(false)

  async function loadConclusion() {
    conclusionLoading.value = true
    try {
      const { data } = await client.get('/testing-plans/conclusion', {
        params: getFilterParams(),
      })
      conclusion.value = data
    } finally {
      conclusionLoading.value = false
    }
  }

  async function copyConclusion() {
    const text = conclusion.value?.summary ?? ''
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success('结论已复制')
    } catch {
      // 非安全上下文/权限被拒时降级提示，不影响其它操作
      ElMessage.warning('复制失败，请手动选择复制')
    }
  }

  async function downloadConclusion() {
    const { data } = await client.get('/testing-plans/conclusion/export', {
      params: getFilterParams(), responseType: 'blob',
    })
    saveBlob(data, '整改情况附件.xlsx')
  }

  return {
    conclusionPanel,
    conclusion,
    conclusionLoading,
    loadConclusion,
    copyConclusion,
    downloadConclusion,
  }
}
