import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'

import client from '../api/client'
import type { TestingPlan } from '../types'
import { cleanUrls } from '../utils/urls'

interface PlanCrudOptions {
  /** 表单模型（由页面持有，含 `id` 表示编辑态） */
  form: Ref<TestingPlan>
  /** 表单实例（保存前做校验） */
  formRef: Ref<FormInstance | undefined>
  /** 字典重载：新增测试类型后刷新候选项 */
  loadTestTypes: () => Promise<unknown>
  /** 组织重载：新增部门后刷新候选项 */
  loadDepartments: () => Promise<unknown>
  /** 保存 / 删除成功后的刷新（列表 + 统计，不重置分页） */
  onSaved: () => Promise<unknown>
}

/**
 * 工单表单弹窗的写入动作（审计 E-2 从 views/TestingPlanList.vue 抽出）。
 *
 * 覆盖：新建/编辑保存（剔除服务端派生字段、URL 清洗）、删除、测试类型与部门的即时新增。
 * 表单 schema（`emptyForm`）、校验规则与字段级 computed 仍留在页面内 —— 它们与模板字段一一对应，
 * 属于「因功能必须与模板同处」的部分。
 */
export function usePlanCrud(opts: PlanCrudOptions) {
  const dialogVisible = ref(false)
  const saving = ref(false)

  async function save() {
    const valid = await opts.formRef.value?.validate().catch(() => false)
    if (!valid) return
    saving.value = true
    try {
      // 以「请求体记录」承载，便于剔除服务端派生字段（不可回写）
      const body: Record<string, unknown> = { ...opts.form.value }
      delete body.testers
      delete body.vuls
      delete body.reports
      delete body.retest_round_count
      delete body.ticket_id
      delete body.ticket_seq
      body.target_urls = cleanUrls(opts.form.value.target_urls)
      if (opts.form.value.id) {
        // 联动创建仅新增时有效，编辑态不提交这两个字段
        delete body.create_nonpen
        delete body.nonpen_test_items
        await client.put(`/testing-plans/${opts.form.value.id}`, body)
      } else {
        await client.post('/testing-plans', body)
      }
      ElMessage.success('保存成功')
      dialogVisible.value = false
      await opts.onSaved()
    } finally {
      saving.value = false
    }
  }

  async function remove(id: number) {
    await client.delete(`/testing-plans/${id}`)
    ElMessage.success('删除成功')
    await opts.onSaved()
  }

  async function addTestType() {
    const { value } = await ElMessageBox.prompt('请输入新的测试类型名称', '新增测试类型', {
      confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    }).catch(() => ({ value: '' }))
    if (!value?.trim()) return
    await client.post('/dict/test_type', { name: value.trim() })
    ElMessage.success('测试类型已新增')
    await opts.loadTestTypes()
    opts.form.value.test_type = value.trim()
  }

  async function addDepartment() {
    const { value } = await ElMessageBox.prompt('请输入新的部门（组织）名称，保存后同步至组织管理', '新增部门', {
      confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    }).catch(() => ({ value: '' }))
    if (!value?.trim()) return
    await client.post('/groups', { name: value.trim(), remark: '' })
    ElMessage.success('部门已新增')
    await opts.loadDepartments()
    opts.form.value.department = value.trim()
  }

  return { dialogVisible, saving, save, remove, addTestType, addDepartment }
}
