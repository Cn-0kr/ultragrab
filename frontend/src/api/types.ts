export type DownloadMode = 'server' | 'proxy' | 'redirect'
export type TaskStatus = 'queued' | 'parsing' | 'ready' | 'downloading' | 'done' | 'error'

export interface VideoMetadata {
  title?: string | null
  thumbnail?: string | null
  duration?: number | null
  uploader?: string | null
  webpage_url?: string | null
  extractor?: string | null
}

export interface FormatOption {
  format_id: string
  ext: string
  label: string
  height?: number | null
  fps?: number | null
  tbr?: number | null
  vcodec?: string | null
  acodec?: string | null
  has_video: boolean
  has_audio: boolean
  filesize?: number | null
  is_recommended?: boolean
  kind: 'progressive' | 'video_only' | 'audio_only'
}

export interface SubtitleLanguage {
  code: string
  name?: string | null
  is_automatic: boolean
}

export interface ParseResult {
  task_id: string
  metadata: VideoMetadata
  formats: FormatOption[]
  subtitles: SubtitleLanguage[]
}

export interface ErrorPayload {
  code: string
  message: string
  hint?: string | null
}

export interface DownloadResponse {
  task_id: string
  mode: DownloadMode
  status: TaskStatus
  download_url?: string | null
}

export interface TaskView {
  task_id: string
  status: TaskStatus
  mode?: DownloadMode | null
  progress: number
  speed?: string | null
  eta?: number | null
  download_url?: string | null
  file_name?: string | null
  metadata?: VideoMetadata | null
  error?: ErrorPayload | null
}

/** Auth / Stripe（与 backend billing_schemas 对齐） */
export interface SubscriptionView {
  status: string
  current_period_end?: number | null
  cancel_at_period_end: boolean
  stripe_price_id?: string | null
}

export interface MeResponse {
  id: string
  email: string
  has_active_subscription: boolean
  subscription?: SubscriptionView | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface CheckoutResponse {
  url: string
}
