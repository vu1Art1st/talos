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
