import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
    // 自定义错误页：顶层路由（不继承主布局）；public 使其在未登录时也可访问
    // ——401 / 404 / 502 常发生在登录之前，若被守卫拦到 /login 则错误页形同虚设。
    {
      path: '/error/:code(\\d{3})',
      name: 'error',
      component: () => import('../views/ErrorPage.vue'),
      meta: { title: '出错了', public: true },
    },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '安全态势' } },
        { path: 'todos', name: 'todos', component: () => import('../views/TodoWorkbench.vue'), meta: { title: '个人待办' } },
        { path: 'messages', name: 'messages', component: () => import('../views/MessageCenter.vue'), meta: { title: '消息中心' } },
        { path: 'vulns', name: 'vulns', component: () => import('../views/VulnList.vue'), meta: { title: '历史漏洞库' } },
        { path: 'vulns/new', name: 'vuln-new', component: () => import('../views/VulnEdit.vue'), meta: { title: '提交漏洞' } },
        { path: 'vulns/:id', name: 'vuln-detail', component: () => import('../views/VulnDetail.vue'), meta: { title: '漏洞详情' } },
        { path: 'vulns/:id/edit', name: 'vuln-edit', component: () => import('../views/VulnEdit.vue'), meta: { title: '编辑漏洞' } },
        { path: 'vulns/:id/retest', name: 'vuln-retest', component: () => import('../views/VulnRetest.vue'), meta: { title: '复测处理' } },
        { path: 'knowledge', name: 'knowledge', component: () => import('../views/KnowledgeList.vue'), meta: { title: '漏洞模板库' } },
        { path: 'reports', name: 'reports', component: () => import('../views/ReportList.vue'), meta: { title: '报告中心' } },
        { path: 'reports/imports', name: 'imports', component: () => import('../views/ImportList.vue'), meta: { title: 'Word 导入' } },
        { path: 'reports/imports/:id', name: 'import-preview', component: () => import('../views/ImportPreview.vue'), meta: { title: '导入预览' } },
        { path: 'reports/:id', name: 'report-editor', component: () => import('../views/ReportEditor.vue'), meta: { title: '报告编辑' } },
        { path: 'assets', name: 'assets', component: () => import('../views/AssetList.vue'), meta: { title: '资产管理' } },
        { path: 'assets/groups', name: 'asset-groups', component: () => import('../views/GroupList.vue'), meta: { title: '组织管理' } },
        { path: 'remote-testings', name: 'remote-testings', component: () => import('../views/RemoteTestingList.vue'), meta: { title: '远程检测' } },
        { path: 'testing-plans', name: 'testing-plans', component: () => import('../views/TestingPlanList.vue'), meta: { title: '渗透测试工单' } },
        { path: 'nonpen-plans', name: 'nonpen-plans', component: () => import('../views/NonpenPlanList.vue'), meta: { title: '漏扫基线工单' } },
        { path: 'spring-actions', name: 'spring-actions', component: () => import('../views/SpringActionList.vue'), meta: { title: '春耕行动' } },
        { path: 'users', name: 'users', component: () => import('../views/UserList.vue'), meta: { title: '用户管理' } },
        { path: 'roles', name: 'roles', component: () => import('../views/RoleList.vue'), meta: { title: '权限管理' } },
        { path: 'audit', name: 'audit', component: () => import('../views/AuditLog.vue'), meta: { title: '审计日志' } },
        { path: 'notify-channels', name: 'notify-channels', component: () => import('../views/NotifyChannelList.vue'), meta: { title: '通知渠道' } },
        { path: 'sla-config', name: 'sla-config', component: () => import('../views/SlaConfig.vue'), meta: { title: 'SLA 配置' } },
        { path: 'report-templates', name: 'report-templates', component: () => import('../views/ReportTemplateList.vue'), meta: { title: '报告模板' } },
        { path: 'tokens', name: 'tokens', component: () => import('../views/TokenList.vue'), meta: { title: '访问令牌' } },
      ],
    },
    // 未匹配的路径：进 404 错误页（原先静默重定向到 /dashboard，会掩盖错误链接且无从发现）
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      redirect: (to) => ({ name: 'error', params: { code: '404' }, query: { from: to.fullPath } }),
    },
  ],
})

router.beforeEach((to) => {
  // 公开页（错误页）不做登录态判断：未登录也必须能看到 401 / 404 / 502 页面
  if (to.meta.public !== true) {
    const token = localStorage.getItem('access_token')
    if (!token && to.name !== 'login') return { name: 'login', query: { redirect: to.fullPath } }
    if (token && to.name === 'login') return { name: 'dashboard' }
  }
  document.title = to.meta.title ? `${to.meta.title} - Talos 漏洞管理平台` : 'Talos 漏洞管理平台'
})

export default router
