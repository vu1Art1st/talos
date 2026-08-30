<template>
  <!-- 全站统一分页：完整 layout + [20,50,100]，替换各视图两种流派的自写分页。
       v-model:page / v-model:size 先行更新，再发 page-change / size-change
       （页面侧典型接法：@page-change="load()" @size-change="onSizeChange"） -->
  <div class="flex items-center justify-end gap-2 pt-3 flex-wrap">
    <el-pagination background layout="total, sizes, prev, pager, next, jumper"
      :total="total" :page-sizes="[20, 50, 100]"
      :current-page="page" :page-size="size"
      @current-change="(p: number) => { emit('update:page', p); emit('page-change', p) }"
      @size-change="(s: number) => { emit('update:size', s); emit('size-change', s) }" />
  </div>
</template>

<script setup lang="ts">
defineProps<{ total: number; page: number; size: number }>()
const emit = defineEmits<{
  (e: 'update:page', v: number): void
  (e: 'update:size', v: number): void
  (e: 'page-change', v: number): void
  (e: 'size-change', v: number): void
}>()
</script>
