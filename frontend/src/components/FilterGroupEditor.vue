<template>
  <div class="filter-group" :class="{ 'filter-group--nested': depth > 1 }">
    <div class="filter-group__head">
      <span class="filter-group__title">{{ root ? '全部条件' : `条件分组（第 ${depth} 层）` }}</span>
      <el-radio-group v-model="group.logic" size="small" @change="emit('change')">
        <el-radio-button value="and">且</el-radio-button>
        <el-radio-button value="or">或</el-radio-button>
      </el-radio-group>
      <span class="filter-group__hint">组内{{ group.logic === 'and' ? '全部满足' : '满足任一' }}</span>
      <el-tooltip content="取反（NOT）：排除满足该分组的记录">
        <el-button
          size="small"
          :type="group.not ? 'danger' : 'default'"
          :plain="!group.not"
          @click="group.not = !group.not; emit('change')"
        >
          非
        </el-button>
      </el-tooltip>
      <el-popconfirm
        v-if="!root"
        title="删除该分组及其全部条件？"
        confirm-button-type="danger"
        width="220"
        @confirm="emit('remove')"
      >
        <template #reference>
          <el-button size="small" text type="danger">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-popconfirm>
    </div>

    <div v-if="!group.children.length" class="filter-group__empty">该分组暂无条件</div>

    <template v-for="(child, i) in group.children" :key="child._uid">
      <div v-if="i > 0" class="filter-group__connector">{{ group.logic === 'or' ? '或' : '且' }}</div>
      <!-- 模板内不做类型收窄（vue-tsc 不支持跨元素分支收窄），以断言显式区分两种子节点 -->
      <FilterGroupEditor
        v-if="isFilterGroup(child)"
        :group="child as FilterGroup"
        :fields="fields"
        :depth="depth + 1"
        @change="emit('change')"
        @remove="removeAt(i)"
      />
      <FilterRuleRow
        v-else
        :rule="child as FilterRule"
        :fields="fields"
        @change="emit('change')"
        @remove="removeAt(i)"
      />
    </template>

    <div class="filter-group__actions">
      <el-button size="small" plain type="primary" @click="addRule">
        <el-icon class="mr-1"><Plus /></el-icon>添加条件
      </el-button>
      <el-button size="small" plain :disabled="depth >= MAX_FILTER_DEPTH" @click="addGroup">
        <el-icon class="mr-1"><FolderAdd /></el-icon>添加分组
      </el-button>
      <span v-if="depth >= MAX_FILTER_DEPTH" class="text-xs text-gray-400">
        已达最大嵌套层级（{{ MAX_FILTER_DEPTH }} 层），如需更深请调整分组结构
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Delete, FolderAdd, Plus } from '@element-plus/icons-vue'

import type { FilterFieldDef, FilterGroup, FilterRule } from '../types'
import { MAX_FILTER_DEPTH, createFilterGroup, createFilterRule, isFilterGroup } from '../utils/filterTree'
import FilterRuleRow from './FilterRuleRow.vue'

// 条件分组编辑器（递归组件）：就地修改传入的 group 对象，任何结构变化冒泡 change 给根节点统一收口。
// depth 从 1（根分组）开始，嵌套层级即查询优先级（先算括号内）；层级由后端同样设限，双向一致。
const props = defineProps<{
  group: FilterGroup
  fields: FilterFieldDef[]
  depth: number
  root?: boolean
}>()

const emit = defineEmits<{
  (e: 'change'): void
  (e: 'remove'): void
}>()

function addRule() {
  props.group.children.push(createFilterRule(props.fields))
  emit('change')
}

function addGroup() {
  props.group.children.push(createFilterGroup())
  emit('change')
}

function removeAt(index: number) {
  props.group.children.splice(index, 1)
  emit('change')
}
</script>

<style scoped>
.filter-group {
  border-radius: 8px;
}
.filter-group--nested {
  border-left: 2px solid var(--tl-border, #e5e7eb);
  background: var(--tl-fill, rgba(127, 127, 127, 0.04));
  padding: 8px 8px 2px 10px;
  margin: 4px 0 8px 8px;
}
.filter-group__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.filter-group__title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--tl-text-2);
  white-space: nowrap;
}
.filter-group__hint {
  font-size: 12px;
  color: var(--tl-text-3);
  white-space: nowrap;
}
.filter-group__empty {
  font-size: 12px;
  color: var(--tl-text-3);
  padding: 2px 0 8px;
}
.filter-group__connector {
  font-size: 12px;
  color: var(--tl-text-3);
  padding: 0 0 4px 4px;
}
.filter-group__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 4px;
}
</style>
