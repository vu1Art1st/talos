import { defineStore } from 'pinia'
import client from '../api/client'
import router from '../router'
import { applyDictMeta } from '../utils/colors'

export interface UserInfo {
  id: number
  username: string
  realname: string
  email: string
  role_name?: string
  permissions: string[]
  must_change_password?: boolean
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as UserInfo | null,
    /**
   * 全局元数据（后端下发的字典 / 色值 / 权限等内容）。
   *
   * 该载荷是**异构袋**：既有「码 → 名称」映射（vul_type / vul_level / vul_status / url_tag…），
   * 也有纯字符串列表（system_type）与嵌套色值表（colors）。逐键建模需覆盖全部后端字典并随其演进，
   * 收益极低而维护成本高 —— 故此处作为审计 E-5 的**保留宽类型边界**，调用方按自身用到的键局部收窄。
   */
  meta: null as Record<string, any> | null,
  }),
  getters: {
    isLoggedIn: () => !!localStorage.getItem('access_token'),
  },
  actions: {
    async login(username: string, password: string) {
      const form = new URLSearchParams()
      form.append('username', username)
      form.append('password', password)
      const { data } = await client.post('/auth/login', form)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      await this.fetchMe()
    },
    async fetchMe() {
      const { data } = await client.get('/auth/me')
      this.user = data
    },
    async fetchMeta() {
      if (this.meta) return this.meta
      const { data } = await client.get('/meta')
      this.meta = data
      applyDictMeta(data)
      return data
    },
    hasPerm(perm: string): boolean {
      const perms = this.user?.permissions ?? []
      return perms.includes('*') || perms.includes(perm)
    },
    logout() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      this.user = null
      router.replace('/login')
    },
  },
})
