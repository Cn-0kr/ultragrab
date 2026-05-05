import type {
  DownloadMode,
  DownloadResponse,
  ErrorPayload,
  ParseResult,
  TaskView,
} from './types'

const API_BASE = '/api'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    let payload: ErrorPayload = { code: 'network_error', message: `HTTP ${resp.status}` }
    try {
      const body = await resp.json()
      if (body?.error) payload = body.error
    } catch {
      // swallow — use default payload
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
}

export function fileUrl(task_id: string): string {
  return `${API_BASE}/files/${encodeURIComponent(task_id)}`
}
