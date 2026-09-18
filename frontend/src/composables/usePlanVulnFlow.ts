import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import client from '../api/client'
import type { Vuln, VulnTransition } from '../types'

/**
 * 工单内单个漏洞的状态流转（审计 E-1 从 PlanWorkflowDrawer.vue 抽出）。
 *
 * @param getStatusName 取状态名（成功提示用；字典缺失时回退状态码）
 * @param onChanged     流转成功后的重载回调（流转会联动计划状态与复测轮数）
 */
export function usePlanVulnFlow(
  getStatusName: (status: number) => string,
  onChanged: () => Promise<void>,
) {
  const transitionsMap = ref<Record<number, VulnTransition[]>>({})

  async function loadTransitions(row: Vuln) {
    // 后端返回 [{status, name}]，直接作为下拉候选
    const { data } = await client.get(`/vulns/${row.id}/transitions`)
    transitionsMap.value[row.id] = data
  }

  async function transition(row: Vuln, status: number) {
    await client.post(`/vulns/${row.id}/transition`, { status })
    ElMessage.success(`已流转为「${getStatusName(status)}」`)
    await onChanged()
  }

  return { transitionsMap, loadTransitions, transition }
}
