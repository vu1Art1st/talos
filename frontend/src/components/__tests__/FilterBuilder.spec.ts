// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import FilterBuilder from '../FilterBuilder.vue'
import type { FilterFieldDef, FilterGroup, FilterNode, FilterRule } from '../../types'
import { countFilterRules, createFilterGroup } from '../../utils/filterTree'

const FIELDS: FilterFieldDef[] = [
  { key: 'system_name', label: '测试系统', type: 'text' },
  { key: 'status', label: '状态', type: 'enum', options: [{ label: '初测完成', value: 30 }] },
]

function mountBuilder(modelValue: FilterGroup = createFilterGroup()) {
  return mount(FilterBuilder, {
    props: { modelValue, fields: FIELDS },
    global: { plugins: [ElementPlus] },
  })
}

type Wrapper = VueWrapper<InstanceType<typeof FilterBuilder>>

/** 最近一次 v-model 输出（条件树） */
function lastTree(wrapper: Wrapper): FilterGroup {
  const events = wrapper.emitted('update:modelValue') as FilterGroup[][] | undefined
  return events!.at(-1)![0]
}

function buttons(wrapper: Wrapper, text: string) {
  return wrapper.findAll('button').filter((b) => b.text().includes(text))
}

async function clickButton(wrapper: Wrapper, text: string, index = 0) {
  const target = buttons(wrapper, text)[index]
  expect(target, `按钮「${text}」应存在`).toBeTruthy()
  await target.trigger('click')
}

const ruleOf = (node: FilterNode | undefined) => node as FilterRule
const groupOf = (node: FilterNode | undefined) => node as FilterGroup

describe('FilterBuilder 聚合筛选条件树编辑器', () => {
  it('空条件树给出引导文案，添加条件后生成默认规则并提示未生效', async () => {
    const wrapper = mountBuilder()
    expect(wrapper.text()).toContain('暂无有效条件')

    await clickButton(wrapper, '添加条件')
    const tree = lastTree(wrapper)
    expect(tree.children).toHaveLength(1)
    expect(ruleOf(tree.children[0])).toMatchObject({
      kind: 'rule', field: 'system_name', op: 'contains', value: '', not: false,
    })
    // 取值未填 → 不参与查询，但保留在界面上
    expect(wrapper.text()).toContain('另有 1 条未填写完整')
    wrapper.unmount()
  })

  it('填写取值后进入实际生效条件，并以可读表达式预览', async () => {
    const wrapper = mountBuilder()
    await clickButton(wrapper, '添加条件')
    await wrapper.find('.filter-value input').setValue('商城')

    expect(ruleOf(lastTree(wrapper).children[0]).value).toBe('商城')
    expect(wrapper.text()).toContain('测试系统 包含 商城')
    expect(wrapper.text()).not.toContain('未填写完整')
    wrapper.unmount()
  })

  it('可添加嵌套分组：组内逻辑可切换为「或」，条件插入到所属分组', async () => {
    const wrapper = mountBuilder()
    await clickButton(wrapper, '添加条件')
    await clickButton(wrapper, '添加分组')

    const nested = lastTree(wrapper).children[1]
    expect(nested.kind).toBe('group')
    expect(wrapper.findAll('.filter-group--nested')).toHaveLength(1)

    // 嵌套分组的「或」单选项（根分组为第一个，嵌套分组为第二个）
    const orRadios = wrapper.findAll('.filter-group--nested input[type="radio"]')
    await orRadios[orRadios.length - 1].setValue()
    expect(groupOf(lastTree(wrapper).children[1]).logic).toBe('or')

    // 嵌套分组内的「添加条件」把规则插到该分组，而非根分组
    const nestedAdd = wrapper
      .find('.filter-group--nested')
      .findAll('button')
      .find((b) => b.text().includes('添加条件'))!
    await nestedAdd.trigger('click')
    expect(countFilterRules(groupOf(lastTree(wrapper).children[1]))).toBe(1)
    expect(countFilterRules(lastTree(wrapper))).toBe(2)
    expect(wrapper.findAll('.filter-group--nested .filter-row')).toHaveLength(1)
    wrapper.unmount()
  })

  it('支持条件级与分组级「非」，删除条件与清空全部同步生效', async () => {
    const wrapper = mountBuilder()
    await clickButton(wrapper, '添加条件')
    await wrapper.find('.filter-row input').setValue('http://x')
    // 条件级「非」（.filter-row 内的默认型按钮即「非」，行内另一个是删除）
    await wrapper.find('.filter-row button.el-button--default').trigger('click')
    expect(ruleOf(lastTree(wrapper).children[0]).not).toBe(true)

    await clickButton(wrapper, '添加分组')
    await wrapper.find('.filter-group--nested .filter-group__head button.el-button--default').trigger('click')
    expect(groupOf(lastTree(wrapper).children[1]).not).toBe(true)

    // 行内删除按钮（文字型；「非」在取反后同为 danger 色，故用 is-text 区分）
    await clickButton(wrapper, '清空全部')
    expect(lastTree(wrapper).children).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无有效条件')

    // 行内删除：仅移除该条条件，不影响其它条件
    await clickButton(wrapper, '添加条件')
    await clickButton(wrapper, '添加条件')
    await wrapper.findAll('.filter-row button.is-text')[0].trigger('click')
    expect(lastTree(wrapper).children).toHaveLength(1)
    wrapper.unmount()
  })

  it('回显历史扁平规则数组（localStorage 旧格式）并渲染为条件行', async () => {
    const legacy = [
      { field: 'system_name', op: 'contains', value: '商城', not: false, connector: 'and' },
      { field: 'status', op: 'eq', value: 30, not: false, connector: 'or' },
    ] as unknown as FilterGroup
    const wrapper = mountBuilder(legacy)

    expect(wrapper.findAll('.filter-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('测试系统 包含 商城')
    expect(wrapper.text()).toContain('或')
    wrapper.unmount()
  })

  it('外部回填值按结构比较决定重建，不覆盖正在编辑的内容', async () => {
    const wrapper = mountBuilder()
    await clickButton(wrapper, '添加条件')
    await wrapper.find('.filter-value input').setValue('商城')

    // 回填等价结构（仅 _uid 不同）→ 输入内容与行数保持不变
    const same = lastTree(wrapper)
    await wrapper.setProps({ modelValue: JSON.parse(JSON.stringify(same)) as FilterGroup })
    expect(wrapper.findAll('.filter-row')).toHaveLength(1)
    expect((wrapper.find('.filter-value input').element as HTMLInputElement).value).toBe('商城')
    wrapper.unmount()
  })
})
