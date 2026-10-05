<template>
  <el-drawer :model-value="visible" size="75%" direction="rtl" :destroy-on-close="true"
             :before-close="onBeforeClose" @update:model-value="onVisibleChange">
    <template #header>
      <div class="flex items-center gap-3">
        <span class="text-base font-semibold">漏扫基线工单 · {{ plan?.system_name || '' }}</span>
        <span v-if="plan" class="font-mono text-sm" style="color: var(--el-color-primary)">
          {{ plan.ticket_id || '-' }}
        </span>
        <span v-if="plan?.linked" class="linked-badge">联动</span>
      </div>
    </template>

    <div v-if="plan" v-loading="loading">
      <el-tabs v-model="activeTab" :before-leave="onTabBeforeLeave">
        <el-tab-pane label="工单信息" name="info" lazy>
          <NonpenPlanInfoPanel ref="infoPanelRef" :mode="infoMode" :plan="plan"
                               @request-edit="infoMode = 'edit'"
                               @saved="onInfoSaved" @cancel="infoMode = 'view'" />
        </el-tab-pane>

        <el-tab-pane label="测试流程" name="flow">
          <div class="flex flex-col gap-4">
            <!-- 测试项流转 -->
            <el-card v-for="t in nonpenItems()" :key="t.key" shadow="never"
                     :class="{ 'item-flow-ignored': isIgnored(t.key) }">
              <div class="flex items-center gap-2 mb-3">
                <el-icon :size="16" style="color: var(--el-color-primary)"><component :is="itemIcon(t.key)" /></el-icon>
                <span class="font-medium">{{ t.name }}</span>
                <span class="tl-tag" :style="softStyle(nonpenItemMeta(statusOf(t.key)).color)">
                  {{ nonpenItemMeta(statusOf(t.key)).label }}
                </span>
                <div class="flex-1" />
                <span v-if="!isIgnored(t.key)" class="text-xs" style="color: var(--tl-text-3)">
                  初测 <b>{{ itemOf(t.key).first_times ?? 0 }}</b> 次 · 复测 <b>{{ itemOf(t.key).retest_times ?? 0 }}</b> 次
                </span>
                <span v-else class="text-xs" style="color: var(--tl-text-3)">不参与统计</span>
              </div>

              <!-- 步骤条：忽略项灰度占位，不显示进度 -->
              <div v-if="isIgnored(t.key)" class="steps mb-3">
                <div class="step-placeholder">已忽略 · 不参与统计</div>
              </div>
              <div v-else class="steps mb-3">
                <template v-for="(s, i) in FLOW_STATES" :key="s.key">
                  <div v-if="i > 0" class="step-line" :class="stepClass(t.key, s.key)" />
                  <div class="step" :class="stepClass(t.key, s.key)">
                    <div class="dot">
                      <el-icon v-if="stepClass(t.key, s.key) === 'done'" :size="12"><Check /></el-icon>
                      <template v-else>{{ i + 1 }}</template>
                    </div>
                    <div class="step-label">{{ s.label }}</div>
                  </div>
                </template>
              </div>

              <div class="flex gap-2 flex-wrap">
                <el-button v-for="action in actionsOf(t.key)" :key="action" size="small"
                           :type="buttonType(action)"
                           :plain="action !== 'ignore' && action !== 'unignore' && action !== 'direct_done' && action !== 'fail'"
                           :disabled="acting === action"
                           @click="doAction(t.key, action)">
                  {{ nonpenActionLabel(action) }}
                </el-button>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Connection, Key, Monitor } from '@element-plus/icons-vue'
import client from '../api/client'
import { nonpenActionLabel, nonpenActions, nonpenItemMeta, nonpenItems, softStyle } from '../utils/colors'
import type { NonpenPlan, PlanDrawerTab } from '../types'
import NonpenPlanInfoPanel from './NonpenPlanInfoPanel.vue'

const props = defineProps<{ visible: boolean; planId: number | null; tab?: PlanDrawerTab }>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'update:tab', v: PlanDrawerTab): void
  (e: 'changed'): void
}>()

const plan = ref<NonpenPlan | null>(null)
const infoPanelRef = ref<InstanceType<typeof NonpenPlanInfoPanel>>()
const infoMode = ref<'view' | 'edit'>('view')
// 路由离开统一走信息面板的离开判定
onBeforeRouteLeave(() => infoPanelRef.value?.confirmLeave?.() ?? true)
// URL（列表页 query）是标签唯一真源；组件内只做受控转发
const activeTab = computed<PlanDrawerTab>({
  get: () => props.tab ?? 'flow',
  set: (v) => emit('update:tab', v),
})

const loading = ref(false)
const acting = ref('')

const FLOW_STATES = [
  { key: 'not_started', label: '未开始' },
  { key: 'testing', label: '初测中' },
  { key: 'wait_retest', label: '初测完成' },
  { key: 'retesting', label: '复测中' },
  { key: 'retest_done', label: '复测完成' },
]

function onVisibleChange(v: boolean) {
  emit('update:visible', v)
}

/** 关闭抽屉前统一走信息面板的离开判定（无修改直接放行） */
async function onBeforeClose(done: () => void) {
  const ok = await (infoPanelRef.value?.confirmLeave?.() ?? true)
  if (!ok) return
  infoMode.value = 'view'
  done()
}

/** 标签切换前统一走离开判定，编辑态有改动时先补存/确认放弃 */
async function onTabBeforeLeave() {
  if (activeTab.value !== 'info') return true
  const ok = await (infoPanelRef.value?.confirmLeave?.() ?? true)
  if (!ok) return false
  infoMode.value = 'view'
  return true
}

async function onInfoSaved() {
  infoMode.value = 'view'
  await load()
  emit('changed')
}

const itemOf = (key: string) => plan.value?.items?.[key] ?? { status: 'not_started', first_times: 0, retest_times: 0 }
const statusOf = (key: string) => itemOf(key).status || 'not_started'
const isIgnored = (key: string) => statusOf(key) === 'ignored'

// 忽略项仅提供「取消忽略」；「复测完成」仅提供置回未开始
const actionsOf = (key: string) => {
  const st = statusOf(key)
  if (st === 'ignored') return ['unignore']
  return nonpenActions(st)
}

function stepClass(itemKey: string, stateKey: string): string {
  const st = statusOf(itemKey)
  if (st === 'retest_done') return 'done'
  const idx = FLOW_STATES.findIndex((s) => s.key === st)
  const curIdx = FLOW_STATES.findIndex((s) => s.key === stateKey)
  if (curIdx < idx) return 'done'
  if (curIdx === idx) return 'current'
  return ''
}

function buttonType(action: string) {
  if (action === 'ignore') return 'danger'
  if (action === 'fail' || action === 'direct_done') return 'warning'
  if (action === 'unignore' || action === 'reset') return 'info'
  return 'primary'
}

function itemIcon(key: string) {
  if (key === 'baseline') return Key
  if (key === 'host') return Monitor
  return Connection
}

async function doAction(itemKey: string, action: string) {
  if (!props.planId) return
  acting.value = action
  try {
    if (action === 'ignore') {
      await client.post(`/nonpen-plans/${props.planId}/items/${itemKey}/ignore`, { ignored: true })
    } else if (action === 'unignore') {
      await client.post(`/nonpen-plans/${props.planId}/items/${itemKey}/ignore`, { ignored: false })
      ElMessage.success('已取消忽略，测试项恢复为未开始（次数已清零）')
    } else {
      await client.post(`/nonpen-plans/${props.planId}/items/${itemKey}/transition`, { action })
    }
    await load()
    emit('changed')
  } finally {
    acting.value = ''
  }
}

async function load() {
  if (!props.planId) return
  loading.value = true
  try {
    const { data } = await client.get<NonpenPlan>(`/nonpen-plans/${props.planId}`)
    plan.value = data
  } finally {
    loading.value = false
  }
}

// 打开时加载（组件常驻，需监听 visible/planId 变化触发刷新，避免首次挂载时 planId 为空导致空白）
watch(
  () => [props.visible, props.planId] as const,
  async ([visible]) => {
    if (!visible || !props.planId) return
    infoMode.value = 'view'
    plan.value = null
    await load()
  },
  { immediate: true },
)
</script>

<style scoped>
/* 忽略项：整行灰度弱化（保留位置） */
.item-flow-ignored {
  opacity: 0.55;
  filter: grayscale(1);
}

/* 自定义步骤条 */
.steps {
  display: flex;
  align-items: flex-start;
}
.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 64px;
  flex: none;
}
.step .dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--tl-text-3);
  background: var(--tl-surface-2);
  border: 1px solid var(--tl-border);
}
.step.done .dot {
  background: var(--tl-success);
  border-color: var(--tl-success);
  color: #fff;
}
.step.current .dot {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
  font-weight: 600;
}
.step-label {
  font-size: 11px;
  color: var(--tl-text-3);
  white-space: nowrap;
}
.step.current .step-label {
  color: var(--el-color-primary);
  font-weight: 500;
}
.step-line {
  flex: 1;
  height: 2px;
  margin-top: 12px;
  background: var(--tl-border);
  min-width: 12px;
}
.step-line.done { background: var(--tl-success); }

.step-placeholder {
  width: 100%;
  text-align: center;
  font-size: 12px;
  color: var(--tl-text-3);
  padding: 12px 0;
  border: 1px dashed var(--tl-border);
  border-radius: 6px;
}
</style>
