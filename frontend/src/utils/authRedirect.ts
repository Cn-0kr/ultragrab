import type { Router } from 'vue-router'

/** 登录/注册成功后的回跳：支持 `/#section`、`/billing/success?...`、仅 `/`；拒绝外站绝对 URL。 */
export function navigateAfterAuth(router: Router, nextRaw: string | undefined | null) {
  const raw = (nextRaw && String(nextRaw).trim()) || '/'
  if (raw.startsWith('http://') || raw.startsWith('https://')) {
    try {
      const u = new URL(raw)
      if (u.origin !== window.location.origin) {
        void router.push('/')
        return
      }
      void router.push({
        path: u.pathname,
        query: Object.fromEntries(u.searchParams.entries()),
        hash: u.hash || undefined,
      })
    } catch {
      void router.push('/')
    }
    return
  }
  try {
    const u = new URL(raw.startsWith('/') ? raw : `/${raw}`, window.location.origin)
    const q = Object.fromEntries(u.searchParams.entries())
    void router.push({ path: u.pathname || '/', query: q, hash: u.hash || undefined })
  } catch {
    void router.push('/')
  }
}
