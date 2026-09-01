<template>
  <div class="space-y-3">
    <FilterToolbar>
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索系统 / 类型 / 部门" clearable
                  @keyup.enter="reload" @clear="reload">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <el-select v-model="rangeKind" placeholder="时间范围" class="!w-28" clearable @change="onRangeChange">
        <el-option v-for="o in DATE_RANGE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-date-picker v-if="rangeKind === 'custom'" v-model="customRange" type="daterange"
                      value-format="YYYY-MM-DD" class="!w-64" start-placeholder="初测完成起"
                      end-placeholder="初测完成止" @change="reload" />
      <el-popover
        :visible="filterVisible"
        trigger="manual"
        placement="bottom-start"
        :width="880"
      >
        <template #reference>
          <el-button :type="filterCount ? 'primary' : 'default'" @click="filterVisible = !filterVisible">
            <el-icon class="mr-1"><Filter /></el-icon>筛选
            <span v-if="filterCount" class="filter-count">{{ filterCount }}</span>
          </el-button>
        </template>
        <div class="filter-panel">
          <div class="mb-2 text-sm font-medium">聚合筛选</div>
          <FilterBuilder v-model="rules" :fields="filterFields" @change="onFiltersChange" />
          <div class="mt-2 text-xs text-gray-400">
            多条件之间用「且 / 或」连接；点「非」对单个条件取反（排除满足该条件的记录）
          </div>
        </div>
      </el-popover>
      <!-- 快捷筛选：三项布尔筛选收纳为下拉多选，勾选任意条件即触发筛选 -->
      <el-popover trigger="click" placement="bottom-start" :width="240">
        <template #reference>
          <el-button :type="quickFilterCount ? 'primary' : 'default'">
            <el-icon class="mr-1"><Filter /></el-icon>快捷筛选
            <span v-if="quickFilterCount" class="filter-count">{{ quickFilterCount }}</span>
          </el-button>
        </template>
        <div class="quick-filter-panel">
          <div class="mb-2 text-sm font-medium">快捷筛选</div>
          <el-checkbox-group v-model="quickFilters" class="quick-filter-group" @change="onQuickFilterChange">
            <el-checkbox value="my_tests">显示当前可测试系统</el-checkbox>
            <el-checkbox value="unclaimed">显示无人认领的测试</el-checkbox>
            <el-checkbox value="pending">显示待办流程</el-checkbox>
          </el-checkbox-group>
        </div>
      </el-popover>
      <template #actions>
      <!-- 导入导出：三操作收纳为下拉，分别对应原「导入模板下载 / 导入 Excel / 导出 Excel」 -->
      <el-dropdown trigger="click" @command="onImportExport">
        <el-button>
          导入导出<el-icon class="ml-1"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="template">
              <el-icon class="mr-1"><Download /></el-icon>导入模板下载
            </el-dropdown-item>
            <el-dropdown-item command="import" :disabled="importing">
              <el-icon class="mr-1"><Upload /></el-icon>导入 Excel
            </el-dropdown-item>
            <el-dropdown-item command="export">
              <el-icon class="mr-1"><Download /></el-icon>导出 Excel
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="importInputRef" type="file" accept=".xlsx" class="hidden" @change="onImportFileChange" />
      <el-button type="primary" class="btn-min" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增渗透测试工单
      </el-button>
      </template>
    </FilterToolbar>

    <el-collapse v-model="statsPanel" class="tl-collapse mb-3">
      <el-collapse-item name="stats">
        <template #title>
          <span class="tl-collapse-title">
            <span class="tl-collapse-title__main">统计概览</span>
            <span class="tl-collapse-title__sub">（与筛选条件联动实时更新）</span>
          </span>
        </template>
        <div class="px-2">
          <!-- 维度勾选：可换行，避免条件过多时溢出边界 -->
          <el-checkbox-group v-model="dims" class="mb-3 flex flex-wrap gap-x-4 gap-y-1">
            <el-checkbox v-for="d in DIMENSIONS" :key="d.key" :value="d.key">{{ d.label }}</el-checkbox>
          </el-checkbox-group>
          <div v-loading="statsLoading" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatCard v-for="d in cardDims" :key="d.key" :label="d.label" :color="d.color" :value="stats[d.key] ?? 0" />
          </div>
          <div v-show="dims.includes('vulns_by_month')" ref="monthChartRef" class="w-full h-64 mt-3" />
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-collapse v-model="conclusionPanel" class="tl-collapse mb-3">
      <el-collapse-item name="conclusion">
        <template #title>
          <span class="tl-collapse-title">
            <span class="tl-collapse-title__main">结论输出</span>
            <span class="tl-collapse-title__sub">（按初测完成时间筛选后生成，可复制 / 下载附件）</span>
          </span>
        </template>
        <div v-loading="conclusionLoading" class="px-2 py-1">
          <div class="conclusion-box">
            <p class="conclusion-text">{{ conclusion.summary || '暂无符合条件的渗透测试工单，请先调整筛选条件' }}</p>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3 mt-3">
            <StatCard label="部门数" :color="STAT_CARD_COLORS.blue" :value="conclusion.departments ?? 0" />
            <StatCard label="系统数" :color="STAT_CARD_COLORS.green" :value="conclusion.systems ?? 0" />
            <StatCard label="存在漏洞系统" :color="STAT_CARD_COLORS.red" :value="conclusion.vuln_systems ?? 0" />
            <StatCard label="漏洞数" :color="STAT_CARD_COLORS.red" :value="conclusion.vulns ?? 0" />
            <StatCard label="未发现安全风险" :color="STAT_CARD_COLORS.green" :value="conclusion.safe_systems ?? 0" />
            <StatCard label="已完成整改" :color="STAT_CARD_COLORS.green" :value="conclusion.fixed_systems ?? 0" />
            <StatCard label="整改中" :color="STAT_CARD_COLORS.orange" :value="conclusion.fixing_systems ?? 0" />
          </div>
          <div class="flex gap-2 mt-3">
            <el-button type="primary" :disabled="!conclusion.summary" @click="copyConclusion">复制结论</el-button>
            <el-button :disabled="!conclusion.summary" @click="downloadConclusion">下载附件</el-button>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" body-style="padding: 0 0 12px">
    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange"
              :default-sort="{ prop: 'receive_time', order: 'descending' }">
      <template #empty>
        <el-empty :image-size="80"
                  :description="pending
                    ? '暂无待办流程，所有渗透测试工单均已进入终态'
                    : '暂无符合条件的渗透测试工单，请调整筛选条件'" />
      </template>
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column label="工单ID" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="font-mono">{{ row.ticket_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="plan_name" label="计划名称" min-width="130" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.plan_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="system_name" label="测试系统" min-width="140" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="test_type" label="测试类型" width="150" show-overflow-tooltip sortable="custom"
                       label-class-name="col-test-type" />
      <el-table-column prop="department" label="所属部门" width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column label="工单提起" width="100">
        <template #default="{ row }">{{ fmtDate(row.ticket_time) }}</template>
      </el-table-column>
      <el-table-column prop="receive_time" label="需求接收" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.receive_time) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="85" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="planStatusDotStyle(row.status)">
            <i></i>{{ statusMap[row.status] ?? row.status }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="first_test_done_time" label="初测完成" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.first_test_done_time) }}</template>
      </el-table-column>
      <el-table-column prop="retest_done_time" label="复测完成" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.retest_done_time) }}</template>
      </el-table-column>
      <el-table-column label="漏洞统计" min-width="230">
        <template #default="{ row }">
          <span class="inline-flex gap-1">
            <span class="tl-tag" :style="levelBadgeStyle(10, row.stat_critical)">超 {{ row.stat_critical }}</span>
            <span class="tl-tag" :style="levelBadgeStyle(20, row.stat_high)">高 {{ row.stat_high }}</span>
            <span class="tl-tag" :style="levelBadgeStyle(30, row.stat_medium)">中 {{ row.stat_medium }}</span>
            <span class="tl-tag" :style="levelBadgeStyle(40, row.stat_low)">低 {{ row.stat_low }}</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="测试人员" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.testers?.length">
            {{ row.testers.map((u: any) => u.realname || u.username).join('、') }}
          </span>
          <span v-else class="text-gray-400">未认领</span>
        </template>
      </el-table-column>
      <el-table-column label="预估/实际人天" width="135">
        <template #default="{ row }">
          <span>{{ row.est_mandays ?? 0 }} / {{ row.actual_mandays ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联漏洞" width="110">
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
      <el-table-column label="关联报告" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.reports?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="success" link>{{ row.reports.length }} 份</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="r in row.reports" :key="r.id" class="flex items-center gap-2">
                <span class="tl-tag" :style="reportStatusSoftStyle(r.status)">{{ reportStatusName(r.status) }}</span>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/reports/${r.id}`)">{{ r.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="复测轮数" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.retest_round_count" placement="left" width="380" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.retest_round_count }} 轮</el-button>
            </template>
            <el-table :data="row.retest_rounds" size="small">
              <el-table-column label="轮次" width="55">
                <template #default="{ row: r }">第 {{ r.round_no }} 轮</template>
              </el-table-column>
              <el-table-column label="开始时间" width="105">
                <template #default="{ row: r }">{{ fmtDateTime(r.start_time) }}</template>
              </el-table-column>
              <el-table-column label="完成时间" width="105">
                <template #default="{ row: r }">
                  <span v-if="!r.done_time" class="tl-tag" :style="softStyle(STAT_CARD_COLORS.orange)">进行中</span>
                  <span v-else>{{ fmtDateTime(r.done_time) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="来源" show-overflow-tooltip>
                <template #default="{ row: r }">{{ r.source || '-' }}</template>
              </el-table-column>
            </el-table>
          </el-popover>
          <span v-else class="text-gray-400">0 轮</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openWorkflow(row)">流程</el-button>
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该计划？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="px-4">
      <TlPagination v-model:page="page" v-model:size="size" :total="total"
                    @page-change="load" @size-change="onSizeChange" />
    </div>
  </el-card>
  </div>

  <el-dialog
             :close-on-click-modal="false" v-model="dialogVisible" :title="form.id ? '编辑渗透测试工单' : '新增渗透测试工单'" width="800px">
    <el-form ref="formRef" :model="form" :rules="planRules" label-width="90px">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-x-4">
        <el-form-item label="计划名称">
          <el-input v-model="form.plan_name" placeholder="与测试系统区分的渗透测试工单名称" />
        </el-form-item>
        <el-form-item label="关联资产">
          <div class="w-full flex gap-2">
            <el-select v-model="form.asset_ids" multiple filterable remote clearable
                       :remote-method="searchAssets" :loading="assetLoading"
                       placeholder="输入资产名称搜索并选择，漏洞录入时将自动带入" class="flex-1"
                       @change="onAssetsChange">
              <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
            </el-select>
            <el-button v-if="!form.id" @click="openCreateAsset">
              <el-icon class="mr-1"><Plus /></el-icon>新增资产
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="测试系统" prop="system_name">
          <el-input v-model="form.system_name" placeholder="影响报告首页名称" />
        </el-form-item>
        <el-form-item label="工单ID">
          <div class="w-full">
            <el-input v-model="form.ticket_id_manual" placeholder="留空则按需求接收日期自动生成（如 20260727-1）"
                      clearable />
            <div v-if="form.id && !form.ticket_id_manual && form.ticket_id"
                 class="text-xs text-gray-400 mt-1">当前自动生成：{{ form.ticket_id }}，留空保存即保持该值</div>
          </div>
        </el-form-item>
        <el-form-item label="测试类型">
          <el-select v-model="form.test_type" filterable clearable placeholder="请选择测试类型" class="w-full">
            <el-option v-for="t in testTypeOptions" :key="t" :label="t" :value="t" />
            <template #footer>
              <el-button size="small" type="primary" link @click="addTestType">
                <el-icon class="mr-1"><Plus /></el-icon>新增测试类型
              </el-button>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="所属部门">
          <el-select v-model="form.department" filterable clearable placeholder="请选择部门" class="w-full">
            <el-option v-for="d in departmentOptions" :key="d" :label="d" :value="d" />
            <template #footer>
              <el-button size="small" type="primary" link @click="addDepartment">
                <el-icon class="mr-1"><Plus /></el-icon>新增部门
              </el-button>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="测试状态">
          <el-select v-model="form.status" class="w-full" :disabled="!statusEditable">
            <el-option v-for="(name, code) in statusMap" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="工单提起">
          <el-date-picker v-model="form.ticket_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="需求接收" prop="receive_time">
          <el-date-picker v-model="form.receive_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="初测完成">
          <el-date-picker v-model="form.first_test_done_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="复测通知">
          <el-date-picker v-model="form.retest_notice_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="复测完成">
          <el-date-picker v-model="form.retest_done_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="超危数">
          <el-input-number v-model="form.stat_critical" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="高危数">
          <el-input-number v-model="form.stat_high" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="中危数">
          <el-input-number v-model="form.stat_medium" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="低危数">
          <el-input-number v-model="form.stat_low" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="预估人天">
          <el-input-number v-model="form.est_mandays" :min="0" :precision="1" :step="0.5" class="!w-full" />
        </el-form-item>
        <el-form-item label="实际人天">
          <div class="w-full flex gap-2">
            <el-input-number v-model="form.actual_mandays" :min="0" :precision="1" :step="0.5" class="flex-1"
                             :disabled="mandaysAuto && !form.actual_mandays_override" />
            <el-button v-if="mandaysAuto && !form.actual_mandays_override" @click="onCorrectMandays">修正</el-button>
            <el-button v-if="mandaysAuto && form.actual_mandays_override" type="warning" plain
                       @click="onCancelMandays">取消修正</el-button>
          </div>
        </el-form-item>
      </div>
      <div v-if="mandaysAuto && !form.actual_mandays_override" class="text-xs text-gray-400 mb-2 pl-[100px]">
        有关联初测报告，实际人天由系统按初测报告测试周期自动计算（复测报告不计入）
      </div>
      <div v-else-if="mandaysAuto && form.actual_mandays_override"
           class="text-xs text-gray-400 mb-2 pl-[100px]">
        已手动修正实际人天，不再随初测报告自动更新；点击「取消修正」恢复系统自动计算
      </div>
      <div v-if="statsAuto" class="text-xs text-gray-400 mb-2 pl-[100px]">
        已有关联漏洞，统计由系统按漏洞等级自动重算
      </div>
      <div v-if="form.id && !statusEditable" class="text-xs text-gray-400 mb-2 pl-[100px]">
        认领该计划后才可修改测试状态
      </div>
      <!-- 创建漏扫基线工单：勾选后展开测试项；保存时自动同步新增漏扫基线工单（共享工单ID，分开管理/统计）。
           挂 prop 以内联展示「至少选择一个测试项」校验 -->
      <el-form-item label=" " prop="nonpen_test_items" class="!mb-4">
        <div class="w-full">
          <div class="tp-create-head" :class="{ on: form.create_nonpen }" @click="toggleCreateNonpen">
            <div class="tp-create-check">
              <el-icon v-if="form.create_nonpen" :size="14"><Check /></el-icon>
            </div>
            <div>
              <div class="tp-create-title">
                创建漏扫基线工单
              </div>
              <div class="tp-create-desc">
                {{ form.create_nonpen
                  ? '勾选后展开测试项；保存时自动同步新增漏扫基线工单，与渗透测试分开管理/统计'
                  : '点击可勾选，勾选后展开测试项选择；保存时自动同步新增漏扫基线工单' }}
              </div>
            </div>
          </div>
          <div v-if="form.create_nonpen" class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
            <div v-for="t in nonpenItems()" :key="t.key" class="test-item-check"
                 :class="{ checked: form.nonpen_test_items.includes(t.key) }" @click="toggleNonpenItem(t.key)">
              <div class="tick"><el-icon v-if="form.nonpen_test_items.includes(t.key)" :size="13"><Check /></el-icon></div>
              <div>
                <div class="ti-name">{{ t.name }}</div>
                <div class="ti-desc">{{ t.desc }}</div>
              </div>
            </div>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="被测系统URL">
        <div class="w-full">
          <el-select v-model="form.target_urls" multiple filterable allow-create default-first-option
                     :reserve-keyword="false" placeholder="选择关联资产后自动带出，也可输入URL回车添加"
                     class="w-full" />
          <div class="text-xs text-gray-400 mt-1">用于报告「测试目标」的被测系统URL/域名；自动带出后可删除，保存后以本列表为准</div>
        </div>
      </el-form-item>
      <el-form-item label="详细描述">
        <el-input v-model="form.detail" type="textarea" :rows="4" placeholder="数据来源等详细信息" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <PlanWorkflowDrawer v-model:visible="workflowVisible" :plan-id="workflowPlanId" @changed="onWorkflowChanged" />

  <AssetFormDialog v-model:visible="assetDialogVisible" :asset="assetPrefill" @saved="onAssetCreated" />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
import { Download, Filter, Upload } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { chartThemeName } from '../utils/chartTheme'
import {
  levelBadgeStyle,
  levelName,
  levelSoftStyle,
  nonpenItems,
  planStatusDotStyle,
  planStatusSoftStyle,
  reportStatusName,
  reportStatusSoftStyle,
  softStyle,
  STAT_CARD_COLORS,
} from '../utils/colors'
import { fmtDate, fmtDateTime } from '../utils/format'
import { saveBlob } from '../utils/download'
import { DATE_RANGE_OPTIONS, computeDateRange } from '../utils/dateRange'
import { assetUrls, cleanUrls, mergeUrls } from '../utils/urls'
import PlanWorkflowDrawer from '../components/PlanWorkflowDrawer.vue'
import StatCard from '../components/StatCard.vue'
import AssetFormDialog from '../components/AssetFormDialog.vue'
import FilterBuilder from '../components/FilterBuilder.vue'
import FilterToolbar from '../components/FilterToolbar.vue'
import TlPagination from '../components/TlPagination.vue'
import { useAssetSelect } from '../composables/useAssetSelect'
import { useDictOptions } from '../composables/useDictOptions'
import { useListPage } from '../composables/useListPage'
import type { FilterFieldDef, FilterRule } from '../components/FilterBuilder.vue'

const auth = useAuthStore()
const router = useRouter()
const { items, total, page, size, search, sort, loading, load, onSortChange, onSizeChange } = useListPage('/testing-plans', {
  defaultSort: { prop: 'receive_time', order: 'desc' },
  extraParams: filterParams,
})
// 快捷筛选：三项布尔筛选收敛为单个下拉多选，myTests/unclaimed/pending 由勾选项派生
const quickFilters = ref<string[]>([])
const myTests = computed(() => quickFilters.value.includes('my_tests'))
const unclaimed = computed(() => quickFilters.value.includes('unclaimed'))
const pending = computed(() => quickFilters.value.includes('pending'))
const quickFilterCount = computed(() => quickFilters.value.length)
function onQuickFilterChange() {
  reload()
}
const dialogVisible = ref(false)
const saving = ref(false)
const statusMap = ref<Record<number, string>>({})
const dialogRow = ref<any>(null)
const { testTypes, departments, loadTestTypes, loadDepartments } = useDictOptions()

// ---------- 时间范围筛选（按初测完成时间） ----------
const rangeKind = ref<string>('')
const customRange = ref<[string, string] | null>(null)

function onRangeChange() {
  if (rangeKind.value !== 'custom') customRange.value = null
  reload()
}

// ---------- 结论输出 ----------
const conclusionPanel = ref<string[]>(['conclusion'])
const conclusion = ref<Record<string, any>>({})
const conclusionLoading = ref(false)

async function loadConclusion() {
  conclusionLoading.value = true
  try {
    const { data } = await client.get('/testing-plans/conclusion', { params: filterParams() })
    conclusion.value = data
  } finally {
    conclusionLoading.value = false
  }
}

async function copyConclusion() {
  const text = conclusion.value?.summary ?? ''
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('结论已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

async function downloadConclusion() {
  const { data } = await client.get('/testing-plans/conclusion/export', {
    params: filterParams(), responseType: 'blob',
  })
  saveBlob(data, '整改情况附件.xlsx')
}

// ---------- 聚合筛选 ----------
const filterVisible = ref(false)
const RULES_KEY = 'testing_plan_filters'

// 聚合筛选可选字段（与后端 _PLAN_FILTER_FIELDS 白名单保持一致）
const FILTER_FIELDS = new Set([
  'system_name', 'test_type', 'department', 'receive_time',
  'status', 'first_test_done_time', 'retest_done_time', 'testers',
])

function loadFilterRules(): FilterRule[] {
  try {
    const saved = JSON.parse(localStorage.getItem(RULES_KEY) || 'null')
    if (Array.isArray(saved)) {
      return saved
        .filter((r: any) => r && typeof r.field === 'string' && r.field
          && FILTER_FIELDS.has(r.field) && typeof r.op === 'string')
        .map((r: any) => ({
          field: r.field,
          op: r.op,
          value: r.value ?? '',
          not: !!r.not,
          connector: r.connector === 'or' ? ('or' as const) : ('and' as const),
        }))
    }
  } catch { /* ignore */ }
  return []
}

const rules = ref<FilterRule[]>(loadFilterRules())
function isRuleComplete(r: FilterRule): boolean {
  if (r.op === 'is_empty' || r.op === 'is_not_empty') return true
  if (r.op === 'between') {
    if (!Array.isArray(r.value) || r.value.length !== 2) return false
    const [lo, hi] = r.value as (string | number | null)[]
    return lo !== null && lo !== '' && hi !== null && hi !== ''
  }
  return r.value !== null && r.value !== ''
}
const filterCount = computed(() => rules.value.filter(isRuleComplete).length)
let filterTimer: ReturnType<typeof setTimeout> | null = null

// 规则变化：持久化 + 防抖刷新列表与统计
function onFiltersChange() {
  localStorage.setItem(RULES_KEY, JSON.stringify(rules.value))
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(() => reload(), 250)
}

// 支持聚合筛选的列字段定义（与后端 _PLAN_FILTER_FIELDS 白名单保持一致）
const filterFields = computed<FilterFieldDef[]>(() => [
  { key: 'system_name', label: '测试系统', type: 'text' },
  { key: 'test_type', label: '测试类型', type: 'text', options: testTypes.value.map((t) => ({ label: t, value: t })) },
  { key: 'department', label: '所属部门', type: 'text', options: departments.value.map((d) => ({ label: d, value: d })) },
  { key: 'receive_time', label: '需求接收', type: 'date' },
  {
    key: 'status', label: '状态', type: 'enum',
    options: Object.entries(statusMap.value).map(([k, v]) => ({ label: v, value: Number(k) })),
  },
  { key: 'first_test_done_time', label: '初测完成', type: 'date' },
  { key: 'retest_done_time', label: '复测完成', type: 'date' },
  { key: 'testers', label: '测试人员', type: 'text' },
])

// ---------- 统计面板 ----------
const DIMENSIONS = [
  { key: 'total_plans', label: '工单总数', color: STAT_CARD_COLORS.blue },
  { key: 'retest_done_plans', label: '复测完成数', color: STAT_CARD_COLORS.green },
  { key: 'first_test_count', label: '初测次数', color: STAT_CARD_COLORS.orange },
  { key: 'retest_count', label: '复测次数', color: STAT_CARD_COLORS.red },
  { key: 'total_test_count', label: '总测试次数', color: STAT_CARD_COLORS.gray },
  { key: 'est_mandays_total', label: '预估人天总计', color: STAT_CARD_COLORS.blue },
  { key: 'actual_mandays_total', label: '实际人天总计', color: STAT_CARD_COLORS.green },
  { key: 'remaining_est_mandays', label: '剩余预估人天', color: STAT_CARD_COLORS.orange },
  { key: 'vulns_by_month', label: '按月漏洞数', color: STAT_CARD_COLORS.blue },
] as const
const STATS_DIMS_KEY = 'testing_plan_stats_dims'
const statsPanel = ref<string[]>([])
const dims = ref<string[]>(loadDims())
const stats = ref<Record<string, number>>({})
const statsLoading = ref(false)
const monthChartRef = ref<HTMLElement>()
let monthChart: echarts.ECharts | null = null
let monthChartTheme = ''

function loadDims(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(STATS_DIMS_KEY) || 'null')
    if (Array.isArray(saved) && saved.length) return saved
  } catch { /* ignore */ }
  return DIMENSIONS.map((d) => d.key)
}

// 勾选的计数类维度（排除图表维度）以数字卡片展示
const cardDims = computed(() =>
  DIMENSIONS.filter((d) => d.key !== 'vulns_by_month' && dims.value.includes(d.key)))

watch(dims, (v) => {
  localStorage.setItem(STATS_DIMS_KEY, JSON.stringify(v))
  if (v.includes('vulns_by_month')) nextTick(renderMonthChart)
})

// 折叠面板展开 / 明暗切换时，按新主题重建月度图表（隐藏态 init 会得到 0 尺寸，需在可见后渲染；
// 展开动画约 300ms，动画结束后再 resize 一次兜底）
const theme = useThemeStore()
watch([statsPanel, () => theme.dark], async ([panel]) => {
  if (panel.includes('stats') && dims.value.includes('vulns_by_month')) {
    await nextTick()
    renderMonthChart()
    setTimeout(() => monthChart?.resize(), 320)
  }
})

// 旧数据的值可能不在字典/组织列表中，临时追加以正常回显
const testTypeOptions = computed(() =>
  form.value.test_type && !testTypes.value.includes(form.value.test_type)
    ? [...testTypes.value, form.value.test_type]
    : testTypes.value)
const departmentOptions = computed(() =>
  form.value.department && !departments.value.includes(form.value.department)
    ? [...departments.value, form.value.department]
    : departments.value)

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = (row: any) => row.testers?.some((u: any) => u.id === auth.user?.id) ?? false
const canOperate = (row: any) => isAdmin.value || isTester(row)

// 状态：新建时仅管理员可指定；编辑时须为认领者或管理员
const statusEditable = computed(() =>
  form.value.id ? (dialogRow.value ? canOperate(dialogRow.value) : false) : isAdmin.value)
// 有关联漏洞时统计自动重算，禁止手填
const statsAuto = computed(() => (dialogRow.value?.vuls?.length ?? 0) > 0)
// 有关联初测报告（标题不含「复测」）时实际人天自动计算，禁止手填；复测报告人天不计入统计
const mandaysAuto = computed(() =>
  (dialogRow.value?.reports ?? []).some((r: any) => !(r.title || '').includes('复测')))
// 自动计算的实际人天：初测报告人天之和（与后端 refresh_mandays 口径一致），取消修正时恢复展示
const autoMandays = computed(() =>
  (dialogRow.value?.reports ?? [])
    .filter((r: any) => !(r.title || '').includes('复测'))
    .reduce((s: number, r: any) => s + (r.actual_mandays ?? 0), 0))
// 修正：进入手动输入状态，保存后不再被初测报告自动覆盖
function onCorrectMandays() {
  form.value.actual_mandays_override = true
}
// 取消修正：恢复为初测报告计算的自动值，保存后由系统重新覆盖
function onCancelMandays() {
  form.value.actual_mandays_override = false
  form.value.actual_mandays = autoMandays.value
}

const emptyForm = () => ({
  id: null as number | null,
  plan_name: '',
  system_name: '',
  test_type: '',
  department: '',
  receive_time: '',
  ticket_time: '',
  ticket_id_manual: '',
  first_test_done_time: '',
  retest_notice_time: '',
  retest_done_time: '',
  status: 10,
  asset_ids: [] as number[],
  stat_critical: 0,
  stat_high: 0,
  stat_medium: 0,
  stat_low: 0,
  est_mandays: 0,
  actual_mandays: 0,
  actual_mandays_override: false,
  create_nonpen: false,
  nonpen_test_items: [] as string[],
  target_urls: [] as string[],
  detail: '',
})
const form = ref(emptyForm())
const formRef = ref<FormInstance>()

// 工单表单校验：测试系统必填；联动创建（仅新增时可勾选）的两条跨字段规则与后端校验口径一致
const requireNonpenItems: FormItemRule['validator'] = (_rule, value, callback) => {
  if (!form.value.id && form.value.create_nonpen && !(value ?? []).length) {
    callback(new Error('已勾选「创建漏扫基线工单」，请至少选择一个非渗透测试项'))
  } else {
    callback()
  }
}
const requireTicketSource: FormItemRule['validator'] = (_rule, _value, callback) => {
  if (!form.value.id && form.value.create_nonpen && !form.value.ticket_id_manual && !form.value.receive_time) {
    callback(new Error('已勾选「创建漏扫基线工单」，请填写「需求接收日期」（用于生成共享工单ID）或手动指定工单ID'))
  } else {
    callback()
  }
}
const planRules: FormRules = {
  system_name: [{ required: true, whitespace: true, message: '请填写测试系统', trigger: 'blur' }],
  nonpen_test_items: [{ validator: requireNonpenItems }],
  receive_time: [{ validator: requireTicketSource }],
}

// ---------- 创建漏扫基线工单（联动） ----------
function toggleCreateNonpen() {
  form.value.create_nonpen = !form.value.create_nonpen
  if (!form.value.create_nonpen) form.value.nonpen_test_items = []
}

function toggleNonpenItem(key: string) {
  const i = form.value.nonpen_test_items.indexOf(key)
  if (i >= 0) form.value.nonpen_test_items.splice(i, 1)
  else form.value.nonpen_test_items.push(key)
}

function filterParams(): Record<string, any> {
  const params: Record<string, any> = { search: search.value }
  const range = computeDateRange(rangeKind.value, customRange.value)
  if (range) {
    params.first_test_from = range[0]
    params.first_test_to = range[1]
  }
  const validRules = rules.value.filter(isRuleComplete)
  if (validRules.length) {
    params.filters = JSON.stringify({
      rules: validRules.map(({ field, op, value, not, connector }) => ({
        field, op, value, not, connector,
      })),
    })
  }
  if (myTests.value) params.my_tests = true
  if (unclaimed.value) params.unclaimed = true
  if (pending.value) params.pending = true
  if (sort.prop) {
    params.sort = sort.prop
    params.order = sort.order
  }
  return params
}

async function loadStats() {
  statsLoading.value = true
  try {
    const { data } = await client.get('/testing-plans/stats', { params: filterParams() })
    stats.value = data
    if (dims.value.includes('vulns_by_month')) nextTick(renderMonthChart)
  } finally {
    statsLoading.value = false
  }
}

function renderMonthChart() {
  if (!monthChartRef.value) return
  const themeName = chartThemeName(theme.dark)
  if (monthChart && monthChartTheme !== themeName) {
    monthChart.dispose()
    monthChart = null
  }
  if (!monthChart) {
    monthChart = echarts.init(monthChartRef.value, themeName)
    monthChartTheme = themeName
  }
  const rows = (stats.value as any).vulns_by_month ?? []
  monthChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 30, bottom: 72 },
    title: { text: '按月漏洞数', textStyle: { fontSize: 12.5, fontWeight: 'normal', color: STAT_CARD_COLORS.gray } },
    xAxis: {
      type: 'category', data: rows.map((r: any) => r.month),
      axisLabel: { rotate: 45, fontSize: 10.5, hideOverlap: true },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: rows.map((r: any) => r.count), itemStyle: { color: STAT_CARD_COLORS.blue }, barMaxWidth: 32 }],
  })
  monthChart.resize()
}

// 筛选变化：列表回到首页并同步刷新统计
async function reload() {
  await Promise.all([load(1), loadStats(), loadConclusion()])
}

async function exportExcel() {
  const { data } = await client.get('/testing-plans/export', {
    params: filterParams(), responseType: 'blob',
  })
  saveBlob(data, '渗透测试工单导出.xlsx')
}

async function downloadTemplate() {
  const { data } = await client.get('/testing-plans/import/template', { responseType: 'blob' })
  saveBlob(data, '渗透测试工单导入模板.xlsx')
}

const importing = ref(false)

async function doImport(options: any) {
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', options.file)
    const { data } = await client.post('/testing-plans/import', fd)
    if (data.failed > 0) {
      await ElMessageBox.alert(
        `共 ${data.total} 行，新增 ${data.created} 行，更新 ${data.updated} 行，失败 ${data.failed} 行：<br/>${data.errors.join('<br/>')}`,
        '导入结果', { dangerouslyUseHTMLString: true },
      )
    } else {
      ElMessage.success(`导入完成：新增 ${data.created} 条，更新 ${data.updated} 条`)
    }
    await Promise.all([load(1), loadStats()])
  } finally {
    importing.value = false
  }
}

// ---------- 导入导出下拉 ----------
const importInputRef = ref<HTMLInputElement>()

// 下拉命令分发：分别对应原「导入模板下载 / 导入 Excel / 导出 Excel」，逻辑完全不变
function onImportExport(command: string) {
  if (command === 'template') downloadTemplate()
  else if (command === 'export') exportExcel()
  else if (command === 'import') importInputRef.value?.click()
}

// 隐藏文件选择器触发后走原 doImport 逻辑（沿用原 el-upload 的 http-request 入参结构 { file }）
function onImportFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) doImport({ file })
  input.value = ''
}

async function openDialog(row?: any) {
  dialogRow.value = row ?? null
  form.value = row ? { ...emptyForm(), ...row } : emptyForm()
  form.value.asset_ids = Array.isArray(form.value.asset_ids) ? form.value.asset_ids : []
  form.value.target_urls = Array.isArray(form.value.target_urls) ? form.value.target_urls : []
  assetOptions.value = []
  if (form.value.asset_ids.length) {
    await loadAssetLabels()
    // 编辑进入：target_urls 为空时从关联资产自动带出 URL（与点选资产「自动带出」语义一致，仅空时带出，保存后以本列表为准）
    if (!form.value.target_urls.length) {
      form.value.target_urls = mergeUrls(
        form.value.target_urls,
        form.value.asset_ids.flatMap((id) => assetUrls(assetCache.value[id])),
      )
    }
  }
  resetBaseline([...form.value.asset_ids])
  dialogVisible.value = true
}

// ---------- 关联资产 ----------
const {
  assetOptions, assetLoading, assetCache, assetLabel,
  searchAssets, loadAssetLabels: loadAssetLabelsRaw, cacheAsset, diffIds, resetBaseline, lastKeyword,
} = useAssetSelect()
let assetSearchTimer: ReturnType<typeof setTimeout> | null = null
const assetDialogVisible = ref(false)
const assetPrefill = ref<any>(null)

function loadAssetLabels() {
  return loadAssetLabelsRaw([...form.value.asset_ids])
}

// 新增渗透测试工单时提供"新增资产"入口，保存后自动关联并填充测试系统/所属部门
function openCreateAsset() {
  assetPrefill.value = lastKeyword() ? { name: lastKeyword() } : null
  assetDialogVisible.value = true
}

function onAssetCreated(asset: any) {
  if (!asset?.id) return
  cacheAsset(asset)
  if (!form.value.asset_ids.includes(asset.id)) {
    form.value.asset_ids.push(asset.id)
  }
  // 自动填充测试系统与所属部门（资产信息），仅带出纯系统名称（不含系统类型/子系统），用户仍可手动修改/覆盖
  form.value.system_name = asset.name
  form.value.department = asset.department || ''
  // 新建资产若已带URL，同样并入被测系统URL
  form.value.target_urls = mergeUrls(form.value.target_urls, assetUrls(asset))
  resetBaseline([...form.value.asset_ids])
}

// 点选关联资产后自动带出：被测系统URL（新增/编辑模式均生效，并入所选资产URL，只增不删、可手动删除）；
// 测试系统/所属部门仍仅新增模式带出（仅带出纯系统名称，不含系统类型/子系统），可手动修改
function onAssetsChange(ids: number[]) {
  const added = diffIds(ids)
  if (added.length) {
    form.value.target_urls = mergeUrls(
      form.value.target_urls,
      added.flatMap((id) => assetUrls(assetCache.value[id])),
    )
  }
  if (form.value.id) return
  if (!added.length) return
  const asset = assetCache.value[added[added.length - 1]]
  if (!asset) return
  form.value.system_name = asset.name
  form.value.department = asset.department || ''
}

async function save() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const body = { ...form.value }
    delete (body as any).testers
    delete (body as any).vuls
    delete (body as any).reports
    delete (body as any).retest_rounds
    delete (body as any).retest_round_count
    delete (body as any).ticket_id
    delete (body as any).ticket_seq
    body.target_urls = cleanUrls(form.value.target_urls)
    if (form.value.id) {
      delete (body as any).create_nonpen
      delete (body as any).nonpen_test_items
      await client.put(`/testing-plans/${form.value.id}`, body)
    } else {
      await client.post('/testing-plans', body)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await Promise.all([load(), loadStats()])
  } finally {
    saving.value = false
  }
}

async function addTestType() {
  const { value } = await ElMessageBox.prompt('请输入新的测试类型名称', '新增测试类型', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/dict/test_type', { name: value.trim() })
  ElMessage.success('测试类型已新增')
  await loadTestTypes()
  form.value.test_type = value.trim()
}

async function addDepartment() {
  const { value } = await ElMessageBox.prompt('请输入新的部门（组织）名称，保存后同步至组织管理', '新增部门', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/groups', { name: value.trim(), remark: '' })
  ElMessage.success('部门已新增')
  await loadDepartments()
  form.value.department = value.trim()
}

async function remove(id: number) {
  await client.delete(`/testing-plans/${id}`)
  ElMessage.success('删除成功')
  await Promise.all([load(), loadStats()])
}

// ---------- 流程抽屉 ----------
const workflowVisible = ref(false)
const workflowPlanId = ref<number | null>(null)

function openWorkflow(row: any) {
  workflowPlanId.value = row.id
  workflowVisible.value = true
}

// 抽屉内发生认领/漏洞/报告/复测等变更后刷新列表与统计
async function onWorkflowChanged() {
  await Promise.all([load(), loadStats()])
}

function onResize() {
  monthChart?.resize()
}

onMounted(async () => {
  const meta = await auth.fetchMeta()
  statusMap.value = meta?.testing_plan_status ?? {}
  window.addEventListener('resize', onResize)
  await Promise.all([load(1), loadStats(), loadConclusion(), loadTestTypes(), loadDepartments()])
})

onBeforeUnmount(() => {
  if (filterTimer) clearTimeout(filterTimer)
  window.removeEventListener('resize', onResize)
  monthChart?.dispose()
  monthChart = null
})
</script>

<style scoped>
/* 操作列紧凑排列：压缩按钮间距避免换行 */
:deep(.op-col .cell) {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
:deep(.op-col .el-button) {
  margin-left: 0;
}
/* 表头统一单行：文案+排序箭头不换行，保持各列表头整洁对齐 */
:deep(.el-table th .cell) {
  white-space: nowrap;
}
/* 筛选按钮上的条件数徽标 */
/* 快捷筛选下拉：纵向排列 + 每项可整行点击 */
.quick-filter-panel :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.quick-filter-panel :deep(.el-checkbox) {
  margin-right: 0;
  height: 32px;
  display: flex;
  align-items: center;
}

/* ---------- 创建漏扫基线工单（联动） ---------- */
.tp-create-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px dashed var(--tl-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.tp-create-head:hover { border-color: var(--el-color-primary); }
.tp-create-head.on {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.tp-create-check {
  width: 20px;
  height: 20px;
  flex: none;
  margin-top: 1px;
  border-radius: 50%;
  border: 1px solid var(--tl-border);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.tp-create-head.on .tp-create-check {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: #fff;
}
.tp-create-title { font-size: 13px; font-weight: 500; }
/* 渐变注释：品牌视觉渐变统一色源见 style.css .tl-brand-gradient */
.tp-create-desc { font-size: 12px; margin-top: 2px; color: var(--tl-text-3); }

/* 结论输出：结论文字卡片 */
.conclusion-box {
  padding: 12px 14px;
  border: 1px solid var(--tl-border);
  border-radius: 8px;
  background: var(--tl-surface);
}
.conclusion-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--tl-text-1);
}

/* 统计卡 / 勾选卡 / 折叠标题样式已上提 style.css 全局共用 */</style>

