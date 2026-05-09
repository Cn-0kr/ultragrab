import { ref } from 'vue'
import { api, clearToken, getToken } from '@/api/client'
import type { MeResponse } from '@/api/types'

const user = ref<MeResponse | null>(null)

export function useAuth() {
  async function refresh() {
    if (!getToken()) {
      user.value = null
      return
    }
    try {
      user.value = await api.me()
    } catch {
      user.value = null
    }
  }

  function logout() {
    clearToken()
    user.value = null
  }

  return { user, refresh, logout }
}
