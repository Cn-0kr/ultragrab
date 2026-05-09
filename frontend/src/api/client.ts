import {
  CheckoutResponse,
  DownloadMode,
  DownloadResponse,
  ErrorPayload,
  MeResponse,
  ParseResult,
  TaskView,
  TokenResponse,
} from './types'
import { API_PREFIX } from './config'

const TOKEN_STORAGE_KEY = 'ultragrab_access_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string) {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export class ApiError extends Error {
  code: string
  hint?: string | null

  constructor(payload: ErrorPayload, status: number) {
    super(payload.message)
    this.code = payload.code
    this.hint = payload.hint ?? null
    this.name = `ApiError(${status})`
  }
}

type RequestOpts = RequestInit & { auth?: boolean }

async function request<T>(path: string, init?: RequestOpts): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (init?.auth) {
    const token = getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  const resp = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers,
  })
  if (!resp.ok) {
    let payload: ErrorPayload = { code: 'network_error', message: `HTTP ${resp.status}` }
    try {
      const body = await resp.json()
      if (body?.error) payload = body.error
    } catch {
      // use default payload
    }
    if (init?.auth && resp.status === 401) {
      clearToken()
    }
    throw new ApiError(payload, resp.status)
  }
  if (resp.status === 204) return undefined as unknown as T
  return (await resp.json()) as T
}

export const api = {
  health: () => request<{ status: string; ffmpeg: boolean; time: number }>('/health'),

  parse: (url: string) =>
    request<ParseResult>('/parse', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  startDownload: (params: {
    task_id: string
    format_id: string
    mode: DownloadMode
    subtitle_langs?: string[]
  }) =>
    request<DownloadResponse>('/download', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  task: (task_id: string) => request<TaskView>(`/tasks/${encodeURIComponent(task_id)}`),

  register: (params: { email: string; password: string }) =>
    request<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  login: (params: { email: string; password: string }) =>
    request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  me: () => request<MeResponse>('/auth/me', { method: 'GET', auth: true }),

  /** 创建 Stripe Checkout 会话；需已登录。成功返回 hosted checkout URL（应整页跳转）。 */
  createCheckout: () =>
    request<CheckoutResponse>('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({}),
      auth: true,
    }),
}

export function fileUrl(task_id: string): string {
  return `${API_PREFIX}/files/${encodeURIComponent(task_id)}`
}
