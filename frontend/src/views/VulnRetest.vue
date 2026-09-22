<template>
  <div v-if="vul" class="max-w-5xl space-y-4 pb-6">
    <el-card shadow="never">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-xl font-semibold text-gray-800">{{ vul.title }}</div>
          <div class="flex items-center gap-2 mt-2">
            <span class="tl-tag" :style="levelSoftStyle(vul.level)">
              {{ meta?.vul_level?.[vul.level] }}
            </span>
            <span class="tl-tag" :style="statusSoftStyleWithRetest(vul.status, vul.is_retest)">
              {{ statusLabel(vul.status, vul.is_retest, meta?.vul_status) }}
            </span>
            <span class="text-xs text-gray-400">共 {{ recordCount }} 条复测记录</span>
          </div>
        </div>
        <el-button @click="openEdit">返回编辑</el-button>
      </div>
    </el-card>

    <VulnRetestPanel :vul-id="vulId" @changed="(n: number) => (recordCount = n)">
      <template #actions>
        <div class="flex-1" />
        <el-button @click="onBack">返回</el-button>
      </template>
    </VulnRetestPanel>
  </div>
<!-- 首屏加载占位：避免数据未到时的空白闪现 -->
  <div v-else v-loading="true" class="h-64" element-loading-text="加载中..." />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '../api/client'
import VulnRetestPanel from '../components/VulnRetestPanel.vue'
import { useAuthStore } from '../stores/auth'
import { goBack, withRedirect } from '../composables/useNavBack'
import { levelSoftStyle, statusLabel, statusSoftStyleWithRetest } from '../utils/colors'
import type { RetestRecord, Vuln } from '../types'

// 独立复测处理页：记录增删改主体抽取为 VulnRetestPanel（与测试计划流程抽屉复用），
// 本页保留漏洞信息卡与返回按钮。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const vulId = Number(route.params.id)
const vul = ref<Vuln | null>(null)
const meta = ref<Record<string, Record<number, string>> | null>(null)
const recordCount = ref(0)

/**
 * 来源感知返回（替代裸 router.back()）：直接粘贴 URL 进入时无站内历史，
 * 裸 back 会退回浏览器上一站甚至退出系统，故兜底到漏洞详情。
 */
function onBack() {
  void goBack(router, route, `/vulns/${vulId}`)
}

/** 返回编辑页：把本页地址作为来源透传，编辑页取消/保存据此回到复测页 */
function openEdit() {
  void router.push(withRedirect(`/vulns/${vulId}/edit`, route.fullPath))
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  const [{ data: v }, { data: r }] = await Promise.all([
    client.get<Vuln>(`/vulns/${vulId}`),
    client.get<RetestRecord[]>(`/vulns/${vulId}/retests`),
  ])
  vul.value = v
  recordCount.value = r.length
})
</script>
