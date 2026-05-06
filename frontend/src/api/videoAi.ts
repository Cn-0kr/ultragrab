export interface TranscriptCue {
  start_ms: number
  end_ms: number
  text: string
}

export interface TranscriptResponse {
  task_id: string
  cues: TranscriptCue[]
  char_count: number
  truncated: boolean
}

export interface MindmapResponse {
  task_id: string
  mermaid: string
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export class VideoAiError extends Error {
  code: string
  hint?: string | null

  constructor(code: string, message: string, hint?: string | null) {
    super(message)
    this.code = code
    this.hint = hint ?? null
    this.name = 'VideoAiError'
  }
}

const API_BASE = '/api'

function normalizeHint(raw: unknown): string | null {
  if (raw == null) return null
  if (typeof raw === 'string') return raw
  if (typeof raw === 'number' || typeof raw === 'boolean') return String(raw)
  try {
    return JSON.stringify(raw)
  } catch {
    return String(raw)
  }
}

async function readError(resp: Response): Promise<VideoAiError> {
  let code = 'network_error'
  let message = `HTTP ${resp.status}`
  let hint: string | null = null
  try {
    const body = await resp.json()
    const err = body?.error
    if (err?.code != null) code = String(err.code)
    if (err?.message != null) message = String(err.message)
    hint = normalizeHint(err?.hint)
  } catch {
    /* ignore */
  }
  return new VideoAiError(code, message, hint)
}

export async function postTranscript(
  taskId: string,
  subtitleLangs?: string[],
): Promise<TranscriptResponse> {
  const resp = await fetch(`${API_BASE}/transcript`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, subtitle_langs: subtitleLangs }),
  })
  if (!resp.ok) throw await readError(resp)
  return (await resp.json()) as TranscriptResponse
}

export async function postMindmap(taskId: string, subtitleLangs?: string[]): Promise<MindmapResponse> {
  const resp = await fetch(`${API_BASE}/mindmap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, subtitle_langs: subtitleLangs }),
  })
  if (!resp.ok) throw await readError(resp)
  const data = (await resp.json()) as Record<string, unknown>
  const raw = data.mermaid
  const mermaid =
    typeof raw === 'string' ? raw : raw != null ? JSON.stringify(raw) : ''
  return { task_id: String(data.task_id ?? taskId), mermaid }
}

/** Parse OpenAI-compatible SSE stream; invokes onDelta with accumulated assistant text. */
export async function streamOpenAiSse(
  path: string,
  body: Record<string, unknown>,
  onDelta: (fullText: string, delta: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok) throw await readError(resp)
  const reader = resp.body?.getReader()
  if (!reader) throw new VideoAiError('stream_error', 'No response body')

  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const block of parts) {
      const lines = block.split('\n')
      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue
        const payload = trimmed.slice(5).trim()
        if (payload === '[DONE]') continue
        try {
          const json = JSON.parse(payload) as {
            error?: { code?: string; message?: string }
            choices?: Array<{ delta?: { content?: string } }>
          }
          if (json.error?.message) {
            throw new VideoAiError(json.error.code || 'ai_upstream_error', json.error.message)
          }
          const piece = json.choices?.[0]?.delta?.content
          if (piece) {
            full += piece
            onDelta(full, piece)
          }
        } catch (e) {
          if (e instanceof VideoAiError) throw e
          /* ignore malformed chunk */
        }
      }
    }
  }
  return full
}

export function streamSummarize(
  taskId: string,
  subtitleLangs: string[] | undefined,
  onDelta: (fullText: string, delta: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  return streamOpenAiSse(
    '/summarize',
    { task_id: taskId, subtitle_langs: subtitleLangs },
    onDelta,
    signal,
  )
}

export function streamChat(
  taskId: string,
  messages: ChatMessage[],
  subtitleLangs: string[] | undefined,
  onDelta: (fullText: string, delta: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  return streamOpenAiSse(
    '/chat',
    { task_id: taskId, subtitle_langs: subtitleLangs, messages },
    onDelta,
    signal,
  )
}
