export function formatDuration(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return '--:--'
  const s = Math.floor(seconds)
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = s % 60
  if (hh > 0) {
    return `${hh}:${mm.toString().padStart(2, '0')}:${ss.toString().padStart(2, '0')}`
  }
  return `${mm}:${ss.toString().padStart(2, '0')}`
}

export function formatBytes(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(1)}${units[idx]}`
}

export function clampProgress(p: number): number {
  if (Number.isNaN(p)) return 0
  return Math.max(0, Math.min(1, p))
}

export function formatPercent(p: number): string {
  return `${Math.round(clampProgress(p) * 100)}%`
}

/**
 * 外链封面常在 http 上返回；在 HTTPS 站点或部分浏览器策略下会触发混合内容拦截。
 * 主流 CDN（含 B 站 hdslb）均支持同源 HTTPS，统一升为 https。
 */
export function normalizeThumbnailSrc(url: string): string {
  try {
    const u = new URL(url)
    if (u.protocol === 'http:') {
      u.protocol = 'https:'
    }
    return u.href
  } catch {
    return url
  }
}

export function formatEta(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return ''
  if (seconds <= 0) return ''
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m${s.toString().padStart(2, '0')}s`
}
