<template>
  <!-- 列表页统一筛选工具栏容器（demo-2 filterbar）：
       默认插槽放搜索框 / 字典筛选（等宽），actions 插槽放右侧按钮组；
       空间不足时优先压缩搜索区（.tl-search-field 弹性），按钮永不折行错位 -->
  <div class="tl-filterbar">
    <slot />
    <div class="flex-1 min-w-2"></div>
    <slot name="actions" />
  </div>
</template>
