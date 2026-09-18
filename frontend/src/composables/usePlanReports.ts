import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'

import client from '../api/client'
import type { Report } from '../types'

interface PlanReportsOptions {
  /** 取当前工单 id */
  getPlanId: () => number | null
  /** 取测试系统名（报告标题自动命名用） */
  getSystemName: () => string
  /** 取计划已记录的无漏洞结论（无漏洞闭环表单预填） */
  getNoVulConclusion: () => string
  /** 取当前工单漏洞 id 列表（生成报告默认勾选全部） */
  getVulnIds: () => number[]
  /** 写操作成功后的重载回调 */
  onChanged: () => Promise<void>
  /** 报告被删除后的清理回调（清导出历史与展开态） */
  onReportRemoved?: (reportId: number) => void
}

/**
 * 工单内报告相关动作（审计 E-1 从 PlanWorkflowDrawer.vue 抽出）。
 *
 * 覆盖：生成报告（含相似性检查二次确认）、删除报告、发起复测、无漏洞闭环完结。
 * 抽屉只保留模板与少量展示态，全部报告写操作与表单态集中在此。
 */
export function usePlanReports(opts: PlanReportsOptions) {
  const genFormVisible = ref(false)
  const genTitle = ref('')
  const genVulIds = ref<number[]>([])
  const generating = ref(false)

  // 无漏洞闭环完结表单状态
  const noVulnVisible = ref(false)
  const noVulnConclusion = ref('')
  const noVulnGenReport = ref(true)
  const noVulnTitle = ref('')
  const noVulnSubmitting = ref(false)

  function toggleGenForm() {
    genFormVisible.value = !genFormVisible.value
    if (genFormVisible.value) {
      // 需求8：自动命名「yyyymmdd+测试系统名称+渗透测试报告」
      genTitle.value = `${dayjs().format('YYYYMMDD')}${opts.getSystemName()}渗透测试报告`
      genVulIds.value = opts.getVulnIds()
    }
  }

  /** 相似性检查：与历史报告的标题、所选漏洞及漏洞最后编辑时间完全一致时需二次确认 */
  async function confirmIfSimilar(): Promise<boolean> {
    try {
      const { data } = await client.post('/reports/similarity-check', {
        title: genTitle.value.trim(),
        vul_ids: genVulIds.value,
        testing_plan_id: opts.getPlanId(),
      })
      if (!data.similar) return true
      return await ElMessageBox.confirm(
        `检测到与历史报告《${genTitle.value.trim()}》高度相似（标题、所选漏洞及漏洞最后编辑时间均未变化），是否仍要继续生成？`,
        '生成高度相似报告',
        { confirmButtonText: '仍要生成', cancelButtonText: '取消', type: 'warning' },
      ).then(() => true).catch(() => false)
    } catch {
      // 检查接口异常时不阻断生成流程
      return true
    }
  }

  async function generateReport() {
    generating.value = true
    try {
      if (!(await confirmIfSimilar())) return
      await client.post('/reports/from-vulns', {
        title: genTitle.value.trim(),
        vul_ids: genVulIds.value,
        testing_plan_id: opts.getPlanId(),
      })
      ElMessage.success('报告已生成，计划进入初测完成')
      genFormVisible.value = false
      await opts.onChanged()
    } finally {
      generating.value = false
    }
  }

  async function removeReport(r: Report) {
    await client.delete(`/reports/${r.id}`)
    opts.onReportRemoved?.(r.id)
    ElMessage.success('报告已删除')
    await opts.onChanged()
  }

  async function startRetest(r: Report) {
    await client.post(`/reports/${r.id}/retest`)
    ElMessage.success('已发起复测，漏洞进入复测中，已自动生成复测报告')
    await opts.onChanged()
  }

  function openNoVulnDialog() {
    noVulnConclusion.value = opts.getNoVulConclusion()
    noVulnGenReport.value = true
    // 自动命名：yyyymmdd+测试系统名称+渗透测试报告（无漏洞）
    noVulnTitle.value = `${dayjs().format('YYYYMMDD')}${opts.getSystemName()}渗透测试报告（无漏洞）`
    noVulnVisible.value = true
  }

  async function completeNoVuln() {
    noVulnSubmitting.value = true
    try {
      await client.post(`/testing-plans/${opts.getPlanId()}/complete-no-vuln`, {
        conclusion: noVulnConclusion.value,
        generate_report: noVulnGenReport.value,
        title: noVulnGenReport.value ? noVulnTitle.value.trim() : '',
      })
      ElMessage.success('已确认无漏洞，计划流转为「测试通过」')
      noVulnVisible.value = false
      await opts.onChanged()
    } finally {
      noVulnSubmitting.value = false
    }
  }

  return {
    genFormVisible,
    genTitle,
    genVulIds,
    generating,
    noVulnVisible,
    noVulnConclusion,
    noVulnGenReport,
    noVulnTitle,
    noVulnSubmitting,
    toggleGenForm,
    generateReport,
    removeReport,
    startRetest,
    openNoVulnDialog,
    completeNoVuln,
  }
}
