import { defineStore } from 'pinia'

// 全站明 / 暗主题：切换 <html> 的 dark 类并持久化到 localStorage
export const useThemeStore = defineStore('theme', {
  state: () => ({
    dark: localStorage.getItem('theme') === 'dark',
  }),
  actions: {
    apply() {
      document.documentElement.classList.toggle('dark', this.dark)
    },
    toggle() {
      this.dark = !this.dark
      localStorage.setItem('theme', this.dark ? 'dark' : 'light')
      this.apply()
    },
    init() {
      this.apply()
    },
  },
})
