<template>
  <el-card shadow="never" v-loading="loading">
    <template #header>
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold">个人访问令牌</span>
        <span class="text-xs text-gray-400">供内部看板与脚本调用开放 API（/api/v1/open/*）</span>
        <div class="flex-1" />
        <el-button class="btn-min" @click="guideVisible = true">
          <el-icon class="mr-1"><Document /></el-icon>接口文档
        </el-button>
        <el-button type="primary" class="btn-min" @click="openCreate">
          <el-icon class="mr-1"><Plus /></el-icon>新建令牌
        </el-button>
      </div>
    </template>

    <el-table :data="items" stripe>
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="令牌前缀" width="160">
        <template #default="{ row }">
          <span class="font-mono text-xs">{{ row.prefix }}…</span>
        </template>
      </el-table-column>
      <el-table-column label="有效期至" width="170" sortable>
        <template #default="{ row }">
          <span :class="isExpired(row) ? 'text-gray-400' : ''">{{ fmtDateTime(row.expires_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="最近使用" width="170">
        <template #default="{ row }"><span class="num">{{ row.last_used_at ? fmtDateTime(row.last_used_at) : '从未使用' }}</span></template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <span class="dot-tag" :style="dotStyle(isExpired(row) ? STAT_CARD_COLORS.gray : STAT_CARD_COLORS.green)">
            <i></i>{{ isExpired(row) ? '已过期' : '有效' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170" sortable>
        <template #default="{ row }"><span class="num">{{ fmtDateTime(row.create_time) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-popconfirm title="吊销后无法恢复，确认吊销？" @confirm="revoke(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>吊销</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无访问令牌，可新建供看板或脚本集成使用" :image-size="80" />
      </template>
    </el-table>

    <TlPagination v-model:page="page" v-model:size="size" :total="total"
                  @page-change="load" @size-change="onSizeChange" />
  </el-card>

  <!-- 新建令牌 -->
  <el-dialog :close-on-click-modal="false" v-model="createVisible" title="新建访问令牌" width="480px">
    <el-form :model="createForm" label-width="90px">
      <el-form-item label="名称" required>
        <el-input v-model="createForm.name" maxlength="64" placeholder="例如：安全大屏看板" />
      </el-form-item>
      <el-form-item label="有效期" required>
        <el-radio-group v-model="createForm.expire_days">
          <el-radio-button v-for="d in [7, 30, 90, 365]" :key="d" :value="d">{{ d }} 天</el-radio-button>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="create">创建</el-button>
    </template>
  </el-dialog>

  <!-- 明文令牌仅展示一次 -->
  <el-dialog :close-on-click-modal="false" v-model="tokenVisible" title="令牌已创建" width="640px">
    <el-alert type="warning" :closable="false" show-icon class="mb-3"
              title="请立即复制保存：明文令牌仅此一次展示，关闭后无法再查看。" />
    <el-input :model-value="createdToken" readonly type="textarea" :rows="3" class="font-mono" />
    <template #footer>
      <el-button @click="tokenVisible = false">关闭</el-button>
      <el-button type="primary" @click="copyToken">复制令牌</el-button>
    </template>
  </el-dialog>

  <!-- 开放 API 访问指南（docs/OPEN_API_GUIDE.md 构建期内联） -->
  <el-drawer v-model="guideVisible" title="开放 API 访问指南" size="800px">
    <div class="md-doc" v-html="guideHtml"></div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Plus } from '@element-plus/icons-vue'
import client from '../api/client'
import { useListPage } from '../composables/useListPage'
import { dotStyle, STAT_CARD_COLORS } from '../utils/colors'
import TlPagination from '../components/TlPagination.vue'
import { fmtDateTime } from '../utils/format'
import { renderMarkdown } from '../utils/markdown'
import guideMd from '../../../docs/OPEN_API_GUIDE.md?raw'

const { items, total, page, size, loading, load, onSizeChange } = useListPage('/pats')

const guideVisible = ref(false)
const guideHtml = computed(() => renderMarkdown(guideMd))

const createVisible = ref(false)
const creating = ref(false)
const tokenVisible = ref(false)
const createdToken = ref('')
const createForm = reactive({ name: '', expire_days: 30 })

const isExpired = (row: any) => new Date(row.expires_at).getTime() <= Date.now()

function openCreate() {
  createForm.name = ''
  createForm.expire_days = 30
  createVisible.value = true
}

async function create() {
  if (!createForm.name.trim()) return ElMessage.warning('请填写令牌名称')
  creating.value = true
  try {
    const { data } = await client.post('/pats', {
      name: createForm.name.trim(), expire_days: createForm.expire_days,
    })
    createVisible.value = false
    createdToken.value = data.token
    tokenVisible.value = true
    await load()
  } finally {
    creating.value = false
  }
}

async function revoke(id: number) {
  await client.delete(`/pats/${id}`)
  ElMessage.success('已吊销')
  await load()
}

async function copyToken() {
  await navigator.clipboard.writeText(createdToken.value)
  ElMessage.success('已复制到剪贴板')
}

onMounted(load)
</script>

<style scoped>
/* 指南抽屉排版：v-html 内容不带 scoped 属性，须用 :deep；色值全部走 --tl-* 令牌保证明暗两态 */
.md-doc {
  font-size: 13.5px;
  line-height: 1.75;
  color: rgb(var(--tl-gray-700));
}
.md-doc :deep(h1),
.md-doc :deep(h2),
.md-doc :deep(h3),
.md-doc :deep(h4) {
  color: rgb(var(--tl-gray-800));
  font-weight: 600;
  line-height: 1.4;
  margin: 20px 0 10px;
}
.md-doc :deep(h1) { font-size: 18px; }
.md-doc :deep(h2) {
  font-size: 15.5px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgb(var(--tl-gray-200));
}
.md-doc :deep(h3) { font-size: 14px; }
.md-doc :deep(h4) { font-size: 13.5px; }
.md-doc :deep(p) { margin: 8px 0; }
.md-doc :deep(ul),
.md-doc :deep(ol) { padding-left: 20px; margin: 8px 0; }
.md-doc :deep(li) { margin: 3px 0; }
.md-doc :deep(code) {
  font-family: var(--tl-mono);
  font-size: 12.5px;
  background: rgb(var(--tl-gray-100));
  border: 1px solid rgb(var(--tl-gray-200));
  border-radius: 4px;
  padding: 1px 5px;
}
.md-doc :deep(pre) {
  background: rgb(var(--tl-gray-100));
  border: 1px solid rgb(var(--tl-gray-200));
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
  margin: 10px 0;
}
.md-doc :deep(pre code) { background: none; border: none; padding: 0; }
.md-doc :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 12.5px;
}
.md-doc :deep(th),
.md-doc :deep(td) {
  border: 1px solid rgb(var(--tl-gray-200));
  padding: 5px 8px;
  text-align: left;
  vertical-align: top;
}
.md-doc :deep(th) {
  background: rgb(var(--tl-gray-100));
  color: rgb(var(--tl-gray-800));
  font-weight: 600;
}
.md-doc :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--tl-primary);
  background: rgb(var(--tl-gray-100));
  border-radius: 0 6px 6px 0;
  color: rgb(var(--tl-gray-600));
}
.md-doc :deep(hr) { border: none; border-top: 1px solid rgb(var(--tl-gray-200)); margin: 16px 0; }
.md-doc :deep(a) { color: var(--tl-accent); }
</style>
