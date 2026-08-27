// 工单 / 资产联动选择：报告导入确认、批量关联工单对话框共用。
// 规则（与 ImportPreview 原逻辑一致）：
// - planLabel：工单下拉展示「工单ID-计划名称-测试系统」，空值省略对应段
// - filteredAssets：关联工单后资产候选 = 工单 asset_ids 优先 → system_name 匹配 → 全量（允许手动选）
// - 选定工单后自动联动默认资产：工单 asset_ids 首个 → 测试系统名匹配首个 → 置空（不自动新建）
import { computed, ref, watch } from 'vue'

export function usePlanAssetLink(
  getPlans: () => any[],
  getAssets: () => any[],
) {
  const planId = ref<number | null>(null)
  const assetId = ref<number | null>(null)

  function planLabel(p: any) {
    return [p.ticket_id, p.plan_name, p.system_name].filter(Boolean).join('-')
  }

  const filteredAssets = computed(() => {
    const plan = getPlans().find((p) => p.id === planId.value)
    if (plan?.asset_ids?.length) {
      const ids = new Set(plan.asset_ids)
      return getAssets().filter((a) => ids.has(a.id))
    }
    if (plan?.system_name) {
      const matched = getAssets().filter((a) => a.name === plan.system_name)
      if (matched.length) return matched
    }
    return getAssets()
  })

  watch(planId, (val) => {
    const plan = getPlans().find((p) => p.id === val)
    if (!plan) {
      assetId.value = null
      return
    }
    if (plan.asset_ids?.length) {
      const first = getAssets().find((a) => a.id === plan.asset_ids[0])
      assetId.value = first ? first.id : (getAssets().find((a) => a.name === plan.system_name)?.id ?? null)
    } else {
      assetId.value = plan.system_name
        ? (getAssets().find((a) => a.name === plan.system_name)?.id ?? null)
        : null
    }
  })

  return { planId, assetId, planLabel, filteredAssets }
}
