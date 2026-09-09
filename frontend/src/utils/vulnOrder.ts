/**
 * 渗透测试工单流程抽屉的漏洞排序（需求5/7）：
 * 按危害等级升序（level 小=超危/高危）；同等级优先按 Word 导入解析序号（seq = 原报告序号），
 * 使历史导入数据（修复前漏洞 id 与报告序号错位）也能按原报告顺序展示；
 * 非 Word 导入的漏洞无 seq 映射，排在同等级导入漏洞之后，再按录入时间 / id 兜底。
 */
export function sortPlanVulns<
  T extends { id: number; level?: number | null; submit_time?: string | null },
>(items: T[], importSeq: Record<number, number> = {}): T[] {
  const seqOf = (id: number) => importSeq[id]
  return [...items].sort(
    (a, b) =>
      (a.level ?? 99) - (b.level ?? 99) ||
      (seqOf(a.id) ?? Number.MAX_SAFE_INTEGER) - (seqOf(b.id) ?? Number.MAX_SAFE_INTEGER) ||
      new Date(a.submit_time ?? 0).getTime() - new Date(b.submit_time ?? 0).getTime() ||
      a.id - b.id,
  )
}
