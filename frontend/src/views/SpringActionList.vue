<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索报告编号 / 系统 / 公文文号" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button type="primary" class="btn-min" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增春耕行动
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="70"
                       :index="(i: number) => (page - 1) * 20 + i + 1" />
      <el-table-column prop="report_no" label="报告编号" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="system_name" label="对应系统" min-width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="year" label="年度" width="90" sortable="custom">
        <template #default="{ row }">{{ row.year || '-' }}</template>
      </el-table-column>
      <el-table-column prop="phase" label="阶段" width="110" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.phase || '-' }}</template>
      </el-table-column>
      <el-table-column label="涉及漏洞" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.vuls?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.vuls.length }} 个</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="v in row.vuls" :key="v.id" class="flex items-center gap-2">
                <span class="tl-tag" :style="levelSoftStyle(v.level)">
                  {{ levelName(v.level) }}
                </span>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/vulns/${v.id}`)">{{ v.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="appeal_success" label="申诉结果" width="100" sortable="custom">
        <template #default="{ row }">
          <span class="tl-tag" :style="row.appeal_success ? softStyle(STAT_CARD_COLORS.green) : softStyle(STAT_CARD_COLORS.gray)">
            {{ row.appeal_success ? '申诉成功' : '未申诉/失败' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="score_deduction" label="最终扣分" width="100" sortable="custom">
        <template #default="{ row }">{{ row.score_deduction }}</template>
      </el-table-column>
      <el-table-column prop="doc_no" label="公文文号" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该记录？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无春耕行动记录，点击「新增春耕行动」创建" :image-size="80" />
      </template>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <el-dialog
             :close-on-click-modal="false" v-model="dialogVisible" :title="form.id ? '编辑春耕行动' : '新增春耕行动'" width="640px">
    <el-form :model="form" label-width="90px">
      <el-form-item label="报告编号" required>
        <el-input v-model="form.report_no" placeholder="原始报告编号" />
      </el-form-item>
      <el-form-item label="对应系统">
        <el-input v-model="form.system_name" />
      </el-form-item>
      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="年度">
          <el-date-picker v-model="form.year" type="year" value-format="YYYY" placeholder="选择年度" class="!w-full" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-input v-model="form.phase" placeholder="如：第一阶段" />
        </el-form-item>
      </div>
      <el-form-item label="涉及漏洞">
        <el-select v-model="form.vul_ids" multiple filterable class="w-full" placeholder="可多选">
          <el-option v-for="v in vulns" :key="v.id" :label="v.title" :value="v.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="申诉成功">
        <el-switch v-model="form.appeal_success" />
      </el-form-item>
      <el-form-item label="最终扣分">
        <el-input-number v-model="form.score_deduction" :min="0" :step="0.5" class="!w-full" />
      </el-form-item>
      <el-form-item label="公文文号">
        <el-input v-model="form.doc_no" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!form.report_no" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import client from '../api/client'
import { useCrudDialog } from '../composables/useCrudDialog'
import { useListPage } from '../composables/useListPage'
import { levelName, levelSoftStyle, softStyle, STAT_CARD_COLORS } from '../utils/colors'

const router = useRouter()
const { items, total, page, search, loading, load, onSortChange } = useListPage('/spring-actions')
const vulns = ref<any[]>([])

const { dialogVisible, saving, form, openDialog: openCrud, submit: save } = useCrudDialog({
  empty: () => ({
    id: null as number | null,
    report_no: '',
    system_name: '',
    year: '',
    phase: '',
    appeal_success: false,
    score_deduction: 0,
    doc_no: '',
    vul_ids: [] as number[],
  }),
  save: async (f) => {
    const body = { ...f }
    delete (body as any).vuls
    if (f.id) {
      await client.put(`/spring-actions/${f.id}`, body)
    } else {
      await client.post('/spring-actions', body)
    }
  },
  afterSave: () => load(),
})

async function openDialog(row?: any) {
  openCrud(row ? { ...row, vul_ids: row.vuls?.map((v: any) => v.id) ?? [] } : null)
  if (!vulns.value.length) {
    const { data } = await client.get('/vulns', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    vulns.value = data.items
  }
}

async function remove(id: number) {
  await client.delete(`/spring-actions/${id}`)
  await load()
}

onMounted(() => load(1))
</script>
