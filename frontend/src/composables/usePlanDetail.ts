import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { Report, TestingPlan, Vuln } from '../types'
import { sortPlanVulns } from '../utils/vulnOrder'

/**
 * 工单流程抽屉的数据核心（审计 E-1 从 PlanWorkflowDrawer.vue 抽出）。
 *
 * 职责：工单详情 / 关联漏洞 / 导入序号映射的加载与状态字典懒加载，
 * 以及「认领 / 退出认领」两个计划级动作；变更后的刷新统一走 `reloadAfterChange()`，
 * 避免各动作函数各自「置脏 + 刷新」时出现遗漏。
 *
 * @param getPlanId     取当前工单 id（抽屉关闭或无选中时为 null）
 * @param prefetchJobs  可选：加载完工单后预取各报告的导出历史（保证「导出历史（N）」计数准确）
 */
export function usePlanDetail(
  getPlanId: () => number | null,
  prefetchJobs?: (reportId: number) => Promise<unknown>,
) {
  const auth = useAuthStore()

  const plan = ref<TestingPlan | null>(null)
  const vulns = ref<Vuln[]>([])
  const loading = ref(false)
  // 本次打开抽屉内是否发生过变更（关闭时据此通知父组件刷新列表）
  const dirty = ref(false)
  const statusMap = ref<Record<number, string>>({})
  const vulStatusMap = ref<Record<number, string>>({})
  // 工单漏洞的导入解析序号映射 {vul_id: seq}：历史导入数据（修复前 id 与原报告序号错位）的排序纠偏依据
  const importSeq = ref<Record<number, number>>({})

  async function refresh() {
    const planId = getPlanId()
    if (!planId) return
    loading.value = true
    try {
      const [planResp, vulResp, seqResp] = await Promise.all([
        client.get(`/testing-plans/${planId}`),
        // 需求5：漏洞默认按危害等级降序（level 升序）展示
        client.get('/vulns', {
          params: { testing_plan_id: planId, size: 100, sort: 'level', order: 'asc' },
        }),
        // 导入解析序号映射：同等级内优先按原报告序号排序（端点对旧数据兼容，无映射时回退 submit_time/id）
        client.get(`/testing-plans/${planId}/vuln-order`).catch(() => undefined),
      ])
      plan.value = planResp.data
      importSeq.value = seqResp?.data ?? {}
      vulns.value = sortPlanVulns(vulResp.data.items, importSeq.value)
      // 预取各报告的导出历史，保证「导出历史（N）」计数准确（未展开前即可看到真实数量）
      const reports = planResp.data.reports || []
      if (prefetchJobs) {
        await Promise.all(reports.map((r: Report) => prefetchJobs(r.id).catch(() => undefined)))
      }
    } finally {
      loading.value = false
    }
  }

  /** 状态字典懒加载（/auth/meta）：仅在本次会话首次打开时请求 */
  async function ensureStatusDict() {
    if (Object.keys(statusMap.value).length) return
    const meta = await auth.fetchMeta()
    statusMap.value = meta?.testing_plan_status ?? {}
    vulStatusMap.value = meta?.vul_status ?? {}
  }

  /** 变更后重载并置脏：抽屉内所有写操作统一走此处 */
  async function reloadAfterChange() {
    dirty.value = true
    await refresh()
  }

  /** 认领：仅认领者后续可录入/流转漏洞，故认领后必须重载（testers 变化影响按钮可见性） */
  async function claim() {
    await client.post(`/testing-plans/${getPlanId()}/claim`)
    ElMessage.success('认领成功，已加入测试人员')
    await reloadAfterChange()
  }

  async function quit() {
    await client.post(`/testing-plans/${getPlanId()}/quit`)
    ElMessage.success('已退出该计划')
    await reloadAfterChange()
  }

  return {
    plan,
    vulns,
    loading,
    dirty,
    statusMap,
    vulStatusMap,
    importSeq,
    refresh,
    ensureStatusDict,
    reloadAfterChange,
    claim,
    quit,
  }
}
