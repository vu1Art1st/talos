<template>
  <div class="flex flex-col gap-4">
    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold">SLA 修复时限策略</span>
          <span class="text-xs text-gray-400">
            配置漏洞修复截止时间的计算口径；策略变更默认只影响未来新漏洞，历史数据需显式重算
          </span>
          <div class="flex-1" />
          <el-button class="btn-min" :loading="saving" @click="openRecalc">历史重算</el-button>
          <el-button type="primary" class="btn-min" :loading="saving" @click="saveConfig">保存配置</el-button>
        </div>
      </template>

      <el-form :model="form" label-width="120px" class="max-w-[860px]">
        <el-form-item label="启用 SLA">
          <el-switch v-model="form.enabled" />
          <span class="ml-3 text-xs text-gray-400">关闭后不再为新漏洞计算修复截止时间</span>
        </el-form-item>
        <el-form-item label="计时口径">
          <el-radio-group v-model="form.day_basis">
            <el-radio-button v-for="o in dayBasisOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="默认时限">
          <el-input-number v-model="form.default_days" :min="1" :max="3650" />
          <span class="ml-2 text-xs text-gray-400">天（未单独配置等级的兜底值）</span>
        </el-form-item>
        <el-form-item label="到期前提醒">
          <el-input-number v-model="form.warn_hours" :min="0" :max="8760" />
          <span class="ml-2 text-xs text-gray-400">小时（进入该窗口标记为「即将到期」并触发提醒）</span>
        </el-form-item>
        <el-form-item label="允许延期">
          <el-switch v-model="form.allow_extend" />
          <span class="ml-3 text-xs text-gray-400">关闭后延期接口将拒绝请求</span>
        </el-form-item>
        <el-form-item v-if="form.day_basis === 'workday'" label="工作日">
          <el-checkbox-group v-model="form.workdays">
            <el-checkbox v-for="(name, idx) in WEEK_NAMES" :key="idx" :value="idx">{{ name }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="form.day_basis === 'workday'" label="节假日">
          <el-date-picker v-model="holidayDates" type="dates" value-format="YYYY-MM-DD"
                          format="YYYY-MM-DD" placeholder="选择节假日日期（可多选）" />
          <div class="mt-1 text-xs text-gray-400">
            工作日口径下，节假日与所选工作日之外的星期都顺延；首期不支持调休（补班日）配置
          </div>
        </el-form-item>
        <el-form-item label="停止计时状态">
          <el-checkbox-group v-model="form.stop_statuses">
            <el-checkbox v-for="s in statusOptions" :key="s.status" :value="s.status">{{ s.name }}</el-checkbox>
          </el-checkbox-group>
          <div class="mt-1 text-xs text-gray-400">漏洞进入所选状态后视为闭环，不再计入逾期</div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold">按等级时限</span>
          <span class="text-xs text-gray-400">未配置的等级使用默认时限；停用某等级＝该等级不参与 SLA</span>
          <div class="flex-1" />
          <el-button class="btn-min" @click="addPolicy">新增等级策略</el-button>
        </div>
      </template>
      <el-table :data="policies" stripe>
        <el-table-column label="漏洞等级" width="160">
          <template #default="{ row }">
            <span class="dot-tag" :style="dotStyle(levelColor(row.level))"><i></i>{{ levelName(row.level) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时限（天）" width="200">
          <template #default="{ row }">
            <el-input-number v-model="row.days" :min="1" :max="3650" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="启用" width="100">
          <template #default="{ row }"><el-switch v-model="row.enabled" /></template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200">
          <template #default="{ row }"><el-input v-model="row.remark" size="small" maxlength="255" /></template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right" class-name="op-col">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="savePolicy(row)">保存</el-button>
            <el-popconfirm v-if="row.id" title="删除后该等级回落到默认时限，确认删除？" @confirm="removePolicy(row)">
              <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" v-if="stats">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold">SLA 概览</span>
          <el-tag v-if="!stats.enabled" size="small" type="info">SLA 未启用</el-tag>
        </div>
      </template>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="有 SLA 漏洞" :value="String(stats.sla_total)" :color="STAT_CARD_COLORS.blue" />
        <StatCard label="已逾期" :value="String(stats.overdue)" :color="STAT_CARD_COLORS.red" />
        <StatCard label="逾期率" :value="`${stats.overdue_rate}%`" :color="STAT_CARD_COLORS.orange" />
        <StatCard label="平均修复时长" :value="stats.avg_fix_days === null ? '-' : `${stats.avg_fix_days} 天`"
                  :color="STAT_CARD_COLORS.green" />
      </div>
      <el-table :data="stats.by_level" class="mt-4" stripe>
        <el-table-column label="等级" width="140">
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>
        <el-table-column prop="total" label="总数" width="120" />
        <el-table-column prop="overdue" label="逾期" width="120" />
        <el-table-column label="逾期率" width="120">
          <template #default="{ row }">{{ row.overdue_rate }}%</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="recalcVisible" title="SLA 历史重算" width="520px" :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" show-icon class="mb-3"
                title="重算会按当前策略覆盖历史漏洞的修复截止时间，并记入审计日志。默认只重算未闭环漏洞。" />
      <el-radio-group v-model="recalcScope">
        <el-radio value="open">仅未闭环漏洞</el-radio>
        <el-radio value="all">全部漏洞</el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="recalcVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doRecalc">开始重算</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import StatCard from '../components/StatCard.vue'
import { useAuthStore } from '../stores/auth'
import {
  dotStyle, levelColor, levelName, slaDayBasisOptions, STAT_CARD_COLORS,
} from '../utils/colors'
import type { SlaConfig, SlaPolicy, SlaStats } from '../types'

const auth = useAuthStore()
const WEEK_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const loading = ref(false)
const saving = ref(false)
const policies = ref<SlaPolicy[]>([])
const stats = ref<SlaStats | null>(null)
const recalcVisible = ref(false)
const recalcScope = ref('open')

const form = reactive<SlaConfig>({
  enabled: false,
  day_basis: 'natural',
  default_days: 7,
  warn_hours: 24,
  allow_extend: true,
  workdays: [0, 1, 2, 3, 4],
  holidays: [],
  stop_statuses: [20, 60],
  remark: '',
})

const holidayDates = computed({
  get: () => form.holidays,
  set: (v: string[]) => { form.holidays = v ?? [] },
})

const dayBasisOptions = computed(() => slaDayBasisOptions())
const statusOptions = computed(() => {
  const dict = (auth.meta?.vul_status ?? {}) as Record<string, string>
  return Object.keys(dict).map(k => ({ status: Number(k), name: dict[k] }))
})

async function load() {
  loading.value = true
  try {
    await auth.fetchMeta()
    const [{ data: cfg }, { data: pol }, { data: st }] = await Promise.all([
      client.get('/sla/config'),
      client.get('/sla/policies'),
      client.get('/sla/stats').catch(() => ({ data: null })),
    ])
    Object.assign(form, cfg)
    policies.value = pol
    stats.value = st
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const { data } = await client.put('/sla/config', {
      ...form,
      remark: form.remark ?? '',
    })
    Object.assign(form, data)
    ElMessage.success('SLA 配置已保存（仅影响未来新漏洞）')
    stats.value = (await client.get('/sla/stats')).data
  } finally {
    saving.value = false
  }
}

async function savePolicy(row: SlaPolicy) {
  await client.post('/sla/policies', {
    level: row.level, days: row.days, enabled: row.enabled, remark: row.remark ?? '',
  })
  ElMessage.success('等级时限已保存')
  await load()
}

async function removePolicy(row: SlaPolicy) {
  await client.delete(`/sla/policies/${row.id}`)
  ElMessage.success('已删除，该等级回落到默认时限')
  await load()
}

function addPolicy() {
  const used = new Set(policies.value.map(p => p.level))
  const next = [10, 20, 30, 40, 50].find(lv => !used.has(lv))
  if (next === undefined) return ElMessage.warning('五个等级均已有策略')
  policies.value = [...policies.value, { level: next, days: form.default_days, enabled: true, remark: '' }]
}

function openRecalc() {
  recalcScope.value = 'open'
  recalcVisible.value = true
}

async function doRecalc() {
  await ElMessageBox.confirm(
    recalcScope.value === 'all'
      ? '将按当前策略重算**全部**漏洞的截止时间，确认继续？'
      : '将按当前策略重算未闭环漏洞的截止时间，确认继续？',
    '确认重算', { type: 'warning' },
  )
  saving.value = true
  try {
    const { data } = await client.post('/sla/recalculate', { scope: recalcScope.value })
    recalcVisible.value = false
    ElMessage.success(data.msg || '重算完成')
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
