<template>
  <div v-if="vul" class="max-w-5xl space-y-4 pb-6">
    <el-card shadow="never" class="!rounded-lg">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-xl font-semibold text-gray-800">{{ vul.title }}</div>
          <div class="flex items-center gap-2 mt-2">
            <span class="tl-tag" :style="levelSoftStyle(vul.level)">
              {{ meta?.vul_level?.[vul.level] }}
            </span>
            <span class="tl-tag" :style="statusSoftStyleEx(vul.status, vul.is_retest)">
              {{ statusLabel(vul.status, vul.is_retest, meta?.vul_status) }}
            </span>
            <span class="text-xs text-gray-400">共 {{ recordCount }} 条复测记录</span>
          </div>
        </div>
        <el-button @click="router.push(`/vulns/${vulId}/edit`)">返回编辑</el-button>
      </div>
    </el-card>

    <VulnRetestPanel :vul-id="vulId" @changed="(n: number) => (recordCount = n)">
      <template #actions>
        <div class="flex-1" />
        <el-button @click="router.back()">返回</el-button>
      </template>
    </VulnRetestPanel>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '../api/client'
import VulnRetestPanel from '../components/VulnRetestPanel.vue'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, statusLabel, statusSoftStyleEx } from '../utils/colors'

// 独立复测处理页：记录增删改主体抽取为 VulnRetestPanel（与测试计划流程抽屉复用），
// 本页保留漏洞信息卡与返回按钮。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const vulId = Number(route.params.id)
const vul = ref<any>(null)
const meta = ref<any>(null)
const recordCount = ref(0)

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  const [{ data: v }, { data: r }] = await Promise.all([
    client.get(`/vulns/${vulId}`),
    client.get(`/vulns/${vulId}/retests`),
  ])
  vul.value = v
  recordCount.value = r.length
})
</script>
