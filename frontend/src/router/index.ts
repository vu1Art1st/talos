import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '安全态势' } },
        { path: 'vulns', name: 'vulns', component: () => import('../views/VulnList.vue'), meta: { title: '漏洞管理' } },
        { path: 'vulns/new', name: 'vuln-new', component: () => import('../views/VulnEdit.vue'), meta: { title: '提交漏洞' } },
        { path: 'vulns/:id', name: 'vuln-detail', component: () => import('../views/VulnDetail.vue'), meta: { title: '漏洞详情' } },
        { path: 'vulns/:id/edit', name: 'vuln-edit', component: () => import('../views/VulnEdit.vue'), meta: { title: '编辑漏洞' } },
        { path: 'vulns/:id/retest', name: 'vuln-retest', component: () => import('../views/VulnRetest.vue'), meta: { title: '复测处理' } },
        { path: 'knowledge', name: 'knowledge', component: () => import('../views/KnowledgeList.vue'), meta: { title: '漏洞知识库' } },
        { path: 'reports', name: 'reports', component: () => import('../views/ReportList.vue'), meta: { title: '报告中心' } },
        { path: 'reports/imports', name: 'imports', component: () => import('../views/ImportList.vue'), meta: { title: 'Word 导入' } },
        { path: 'reports/imports/:id', name: 'import-preview', component: () => import('../views/ImportPreview.vue'), meta: { title: '导入预览' } },
        { path: 'reports/:id', name: 'report-editor', component: () => import('../views/ReportEditor.vue'), meta: { title: '报告编辑' } },
        { path: 'assets', name: 'assets', component: () => import('../views/AssetList.vue'), meta: { title: '资产管理' } },
        { path: 'assets/groups', name: 'asset-groups', component: () => import('../views/GroupList.vue'), meta: { title: '组织管理' } },
        { path: 'remote-testings', name: 'remote-testings', component: () => import('../views/RemoteTestingList.vue'), meta: { title: '远程检测' } },
        { path: 'testing-plans', name: 'testing-plans', component: () => import('../views/TestingPlanList.vue'), meta: { title: '渗透测试计划' } },
        { path: 'nonpen-plans', name: 'nonpen-plans', component: () => import('../views/NonpenPlanList.vue'), meta: { title: '非渗透计划' } },
        { path: 'spring-actions', name: 'spring-actions', component: () => import('../views/SpringActionList.vue'), meta: { title: '春耕行动' } },
        { path: 'users', name: 'users', component: () => import('../views/UserList.vue'), meta: { title: '用户与权限' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token && to.name !== 'login') return { name: 'login', query: { redirect: to.fullPath } }
  if (token && to.name === 'login') return { name: 'dashboard' }
  document.title = to.meta.title ? `${to.meta.title} - Talos 漏洞管理平台` : 'Talos 漏洞管理平台'
})

export default router
