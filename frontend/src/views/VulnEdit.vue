<template>
  <div class="h-full min-h-0">
    <VulnFormPanel :plan-id="planId" :edit-id="editId" aside-actions @saved="onSaved">
      <!-- 计划关联提示：渲染在左侧内容区顶部 -->
      <template #notice>
        <div v-if="planId" class="mb-3">
          <span class="ktag">
            本次录入将关联渗透测试工单{{ planName ? `「${planName}」` : '' }}
          </span>
        </div>
      </template>
      <template #actions-left>
        <el-button v-if="editId" type="warning" plain class="w-full !ml-0" @click="openRetest">
          复测
        </el-button>
      </template>
      <template #actions-right>
        <el-button class="w-full !ml-0" @click="onCancel">取消</el-button>
      </template>
    </VulnFormPanel>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '../api/client'
import VulnFormPanel from '../components/VulnFormPanel.vue'
import { goBack, withRedirect } from '../composables/useNavBack'
import { normalizeRedirect } from '../utils/errorPage'
import type { VulnForm } from '../types'

// 独立漏洞提交/编辑页：表单主体抽取为 VulnFormPanel（与测试计划流程抽屉复用），
// 本页仅保留路由行为（计划横幅、复测/取消按钮、保存后跳转）。
const route = useRoute()
const router = useRouter()
const editId = route.name === 'vuln-edit' ? Number(route.params.id) : null
// 从测试计划「录入漏洞」进入时预关联计划
const planId = !editId && route.query.plan_id ? Number(route.query.plan_id) : null
const planName = ref('')

/**
 * 来源页（由跳转方经 `redirect` 参数携带，如工单流程抽屉 → 编辑漏洞）：
 * 存在时取消/保存都原路返回，避免脱离工单上下文；无来源时维持原有去向。
 */
const redirectTarget = computed(() => normalizeRedirect(route.query.redirect))

function onCancel() {
  void goBack(router, route, '/vulns')
}

function openRetest() {
  void router.push(withRedirect(`/vulns/${editId}/retest`, route.fullPath))
}

function onSaved(vulns: VulnForm[]) {
  // replace：避免浏览器后退又回到刚保存的表单页
  if (redirectTarget.value) {
    void router.replace(redirectTarget.value)
  } else if (editId) {
    void router.push(`/vulns/${editId}`)
  } else {
    void router.push(vulns.length === 1 ? `/vulns/${vulns[0].id}` : '/vulns')
  }
}

onMounted(async () => {
  if (planId) {
    const { data } = await client.get(`/testing-plans/${planId}`).catch(() => ({ data: null }))
    planName.value = data?.system_name ?? ''
  }
})
</script>
