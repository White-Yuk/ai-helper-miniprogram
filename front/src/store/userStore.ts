import { create } from 'zustand'

import { fetchMe } from '../services/api'
import type { MeData } from '../types'

interface UserState {
  /** 当前用户信息（含统计与续答） */
  me: MeData | null
  /** 是否正在加载用户信息 */
  loading: boolean
  /** 拉取用户信息（失败时向上抛，由页面提示） */
  loadMe: () => Promise<void>
  /** 退出登录 / 清空（预留） */
  reset: () => void
}

export const useUserStore = create<UserState>((set) => ({
  me: null,
  loading: false,

  loadMe: async () => {
    set({ loading: true })
    try {
      const me = await fetchMe()
      set({ me })
    } finally {
      set({ loading: false })
    }
  },

  reset: () => set({ me: null, loading: false }),
}))
