import { defineStore } from 'pinia'

/** 全局 UI 状态（命令面板等） */
export const useUiStore = defineStore('ui', {
  state: () => ({ cmdkVisible: false }),
  actions: {
    openCmdk() { this.cmdkVisible = true },
    closeCmdk() { this.cmdkVisible = false },
  },
})
