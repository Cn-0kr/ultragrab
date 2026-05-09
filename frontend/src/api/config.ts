/** 与 `client.ts` 一致：开发默认 `/api`（Vite proxy），跨域部署时设 `VITE_API_BASE`。 */
export const API_PREFIX = (() => {
  const base = (import.meta.env.VITE_API_BASE as string | undefined)?.trim().replace(/\/$/, '') ?? ''
  return base ? `${base}/api` : '/api'
})()
