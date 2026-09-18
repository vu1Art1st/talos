import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import client from '../api/client'
import type { QueryParams, Vuln } from '../types'
import { sortPlanVulns } from '../utils/vulnOrder'

/**
 * 「从漏洞库选择并关联到工单」选择器（审计 E-1 从 PlanWorkflowDrawer.vue 抽出）。
 *
 * 拆自抽屉的漏洞关联流程：打开即加载候选、按关键词/等级过滤、勾选后批量关联。
 *
 * @param getPlanId     取当前工单 id
 * @param getLinkedIds  取已关联本工单的漏洞 id（用于选择器禁用与标记）
 * @param onAttached    关联成功后的重载回调（由调用方落到 `reloadAfterChange`）
 */
export function usePlanVulnPicker(
  getPlanId: () => number | null,
  getLinkedIds: () => number[],
  onAttached: () => Promise<void>,
) {
  const vulnPickerVisible = ref(false)
  const pickerLoading = ref(false)
  const pickerSearch = ref('')
  const pickerLevel = ref<number | ''>('')
  const pickerVulns = ref<Vuln[]>([])
  const pickerSelection = ref<Vuln[]>([])
  const pickerAttaching = ref(false)
  // 已关联当前计划的漏洞 ID，用于选择器禁用与标记
  const pickerLinkedIds = computed(() => getLinkedIds())

  async function loadPickerVulns() {
    if (!vulnPickerVisible.value) return
    pickerLoading.value = true
    try {
      // 注意：后端 /vulns 的 size 上限为 100，超出会返回 422
      const params: QueryParams = { size: 100, sort: 'level', order: 'asc' }
      if (pickerSearch.value.trim()) params.search = pickerSearch.value.trim()
      if (pickerLevel.value) params.level = pickerLevel.value
      const { data } = await client.get('/vulns', { params })
      pickerVulns.value = sortPlanVulns(data.items)
    } finally {
      pickerLoading.value = false
    }
  }

  async function openVulnPicker() {
    vulnPickerVisible.value = true
    pickerSearch.value = ''
    pickerLevel.value = ''
    await loadPickerVulns()
  }

  async function attachPickerVulns() {
    pickerAttaching.value = true
    try {
      await client.post(`/testing-plans/${getPlanId()}/attach-vulns`, {
        vul_ids: pickerSelection.value.map((v) => v.id),
      })
      ElMessage.success(`已添加 ${pickerSelection.value.length} 个漏洞到当前计划`)
      vulnPickerVisible.value = false
      await onAttached()
    } finally {
      pickerAttaching.value = false
    }
  }

  return {
    vulnPickerVisible,
    pickerLoading,
    pickerSearch,
    pickerLevel,
    pickerVulns,
    pickerSelection,
    pickerAttaching,
    pickerLinkedIds,
    openVulnPicker,
    loadPickerVulns,
    attachPickerVulns,
  }
}
