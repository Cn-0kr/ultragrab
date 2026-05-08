<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Spinner from './Spinner.vue'
import VideoSummary from './VideoSummary.vue'
import { api, ApiError, fileUrl } from '../api/client'
import type {
  DownloadMode,
  FormatOption,
  ParseResult,
  TaskView,
} from '../api/types'
import {
  formatBytes,
  formatDuration,
  formatEta,
  formatPercent,
  normalizeThumbnailSrc,
} from '../utils/format'

interface TaskEntry {
  id: string
  url: string
  parse?: ParseResult
  selectedFormat?: FormatOption
  mode: DownloadMode
  status:
    | 'idle'
    | 'parsing'
    | 'ready'
    | 'queued'
    | 'downloading'
    | 'done'
    | 'error'
  progress: number
  speed?: string | null
  eta?: number | null
  downloadUrl?: string | null
  fileName?: string | null
  error?: { code: string; message: string; hint?: string | null } | null
  pollingHandle?: number
  thumbnailLoadFailed?: boolean
}

const modes: Array<{ value: DownloadMode; label: string; hint: string }> = [
  {
    value: 'server',
    label: '服务端下载',
    hint: '后端合并最高画质音视频，适合需要最稳定的场景',
  },
  {
    value: 'proxy',
    label: '直链代理',
    hint: '不落盘，通过后端转发，保留 Referer 等头',
  },
  {
    value: 'redirect',
    label: '直链 302',
    hint: '直接跳转到源直链，轻负载（部分平台可能失败）',
  },
]

const urlInput = ref('')
const batchMode = ref(false)
const isSubmitting = ref(false)
const entries = ref<TaskEntry[]>([])
const globalError = ref<string | null>(null)
const inputEl = ref<HTMLTextAreaElement | HTMLInputElement | null>(null)

function focusInput() {
  inputEl.value?.focus()
}

defineExpose({ focusInput })

function splitBatchInput(raw: string): string[] {
  return raw
    .split(/[\s,，;；]+/u)
    .map((item) => item.trim())
    .filter(Boolean)
}

function createEntry(url: string): TaskEntry {
  return reactive({
    id: `local_${Date.now()}_${Math.random().toString(16).slice(2, 6)}`,
    url,
    mode: 'server',
    status: 'parsing',
    progress: 0,
    thumbnailLoadFailed: false,
  }) as TaskEntry
}

function onThumbnailError(entry: TaskEntry) {
  entry.thumbnailLoadFailed = true
}

async function submitInput() {
  globalError.value = null
  const raw = urlInput.value.trim()
  if (!raw) {
    globalError.value = '请粘贴至少一个视频链接。'
    return
  }

  const urls = batchMode.value ? splitBatchInput(raw) : [raw]
  if (urls.length === 0) {
    globalError.value = '没有解析到有效链接。'
    return
  }

  isSubmitting.value = true
  try {
    for (const url of urls) {
      const entry = createEntry(url)
      entries.value.unshift(entry)
      void parseEntry(entry)
    }
    urlInput.value = ''
  } finally {
    isSubmitting.value = false
  }
}

async function parseEntry(entry: TaskEntry) {
  try {
    entry.status = 'parsing'
    entry.error = null
    const res = await api.parse(entry.url)
    entry.parse = res
    entry.thumbnailLoadFailed = false
    entry.status = 'ready'
    const recommended = res.formats.find((f) => f.is_recommended) ?? res.formats[0]
    entry.selectedFormat = recommended
  } catch (err) {
    if (err instanceof ApiError) {
      entry.error = { code: err.code, message: err.message, hint: err.hint }
    } else if (err instanceof Error) {
      entry.error = { code: 'network_error', message: err.message }
    } else {
      entry.error = { code: 'network_error', message: 'Unknown error' }
    }
    entry.status = 'error'
  }
}

function stopPolling(entry: TaskEntry) {
  if (entry.pollingHandle !== undefined) {
    window.clearInterval(entry.pollingHandle)
    entry.pollingHandle = undefined
  }
}

function pollTask(entry: TaskEntry) {
  stopPolling(entry)
  if (!entry.parse) return
  const taskId = entry.parse.task_id
  entry.pollingHandle = window.setInterval(async () => {
    try {
      const view: TaskView = await api.task(taskId)
      entry.progress = view.progress ?? 0
      entry.speed = view.speed
      entry.eta = view.eta
      entry.fileName = view.file_name
      if (view.status === 'done') {
        entry.status = 'done'
        entry.downloadUrl = fileUrl(taskId)
        stopPolling(entry)
      } else if (view.status === 'error') {
        entry.status = 'error'
        entry.error = view.error ?? { code: 'internal', message: '下载失败' }
        stopPolling(entry)
      } else if (view.status === 'downloading') {
        entry.status = 'downloading'
      } else if (view.status === 'queued') {
        entry.status = 'queued'
      }
    } catch (err) {
      entry.status = 'error'
      entry.error =
        err instanceof ApiError
          ? { code: err.code, message: err.message, hint: err.hint }
          : {
              code: 'network_error',
              message: err instanceof Error ? err.message : 'polling failed',
            }
      stopPolling(entry)
    }
  }, 1200)
}

async function startDownload(entry: TaskEntry) {
  if (!entry.parse || !entry.selectedFormat) return
  try {
    entry.error = null
    if (entry.mode !== 'server' && entry.selectedFormat.format_id === 'best_merge') {
      // best_merge requires server merging.
      const fallback = entry.parse.formats.find(
        (f) => f.format_id !== 'best_merge' && f.has_video && f.has_audio,
      )
      if (fallback) {
        entry.selectedFormat = fallback
      } else {
        entry.error = {
          code: 'invalid_format',
          message: '当前模式需要单流格式',
          hint: '请改用服务端模式，或选择一个合并好的格式。',
        }
        entry.status = 'error'
        return
      }
    }
    const resp = await api.startDownload({
      task_id: entry.parse.task_id,
      format_id: entry.selectedFormat.format_id,
      mode: entry.mode,
    })
    if (resp.mode === 'server') {
      entry.status = 'queued'
      entry.progress = 0
      pollTask(entry)
    } else {
      entry.status = 'ready'
      entry.downloadUrl = resp.download_url ?? null
      if (resp.download_url) {
        triggerBrowserDownload(resp.download_url, entry)
      }
    }
  } catch (err) {
    if (err instanceof ApiError) {
      entry.error = { code: err.code, message: err.message, hint: err.hint }
    } else if (err instanceof Error) {
      entry.error = { code: 'network_error', message: err.message }
    }
    entry.status = 'error'
  }
}

function triggerBrowserDownload(href: string, entry: TaskEntry) {
  const a = document.createElement('a')
  a.href = href
  a.rel = 'noopener noreferrer'
  a.target = '_blank'
  const title = entry.parse?.metadata.title
  if (title) {
    a.download = title.replace(/[\\/:*?"<>|]+/g, '_').slice(0, 120)
  }
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function removeEntry(entry: TaskEntry) {
  stopPolling(entry)
  entries.value = entries.value.filter((e) => e.id !== entry.id)
}

function retryEntry(entry: TaskEntry) {
  entry.error = null
  if (!entry.parse) {
    void parseEntry(entry)
  } else {
    void startDownload(entry)
  }
}

function statusLabel(entry: TaskEntry): string {
  switch (entry.status) {
    case 'parsing':
      return '解析中…'
    case 'ready':
      return '解析完成，可选择下载'
    case 'queued':
      return '排队中'
    case 'downloading':
      return '下载中'
    case 'done':
      return '已完成'
    case 'error':
      return '失败'
    default:
      return ''
  }
}

const hasEntries = computed(() => entries.value.length > 0)
</script>

<template>
  <section id="workbench" class="mx-auto max-w-6xl scroll-mt-20 px-4 py-10 md:px-8 md:py-16">
    <div class="card p-6 md:p-10">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-3xl md:text-4xl">把链接粘进来 👇</h2>
          <p class="mt-2 text-ink-soft">
            支持 YouTube / Bilibili / X / TikTok / Facebook / Instagram 等 1800+ 平台公开视频。
          </p>
        </div>
        <label class="flex items-center gap-2 text-sm font-semibold text-ink-soft">
          <input
            v-model="batchMode"
            type="checkbox"
            class="h-4 w-4 accent-brand"
          />
          批量模式（每行 / 逗号 / 空格 分隔）
        </label>
      </div>

      <form class="mt-6 flex flex-col gap-3 md:flex-row md:items-stretch" @submit.prevent="submitInput">
        <template v-if="!batchMode">
          <input
            ref="inputEl"
            v-model="urlInput"
            type="url"
            inputmode="url"
            spellcheck="false"
            placeholder="粘贴视频链接：https://www.youtube.com/watch?v=..."
            class="flex-1 rounded-full border-2 border-ink bg-white px-5 py-4 text-base shadow-sticker-sm focus:outline-none focus:ring-4 focus:ring-brand/30"
          />
        </template>
        <template v-else>
          <textarea
            ref="inputEl"
            v-model="urlInput"
            rows="4"
            spellcheck="false"
            placeholder="每行一个链接，也可用逗号/空格分隔"
            class="flex-1 rounded-[26px] border-2 border-ink bg-white px-5 py-4 text-base shadow-sticker-sm focus:outline-none focus:ring-4 focus:ring-brand/30"
          />
        </template>
        <button
          type="submit"
          class="btn-primary md:min-w-[160px]"
          :disabled="isSubmitting"
        >
          <span v-if="!isSubmitting">立即解析</span>
          <span v-else class="flex items-center gap-2"><Spinner /> 解析中…</span>
        </button>
      </form>

      <p v-if="globalError" class="mt-3 text-sm font-semibold text-red-600">{{ globalError }}</p>

      <p class="mt-4 text-xs text-ink-mute">
        本工具仅用于下载用户有权访问的公开/授权内容。请勿用于绕过 DRM、付费墙或未授权的抓取。
      </p>
    </div>

    <div v-if="hasEntries" class="mt-8 flex flex-col gap-6">
      <article
        v-for="entry in entries"
        :key="entry.id"
        class="card overflow-hidden"
      >
        <div class="grid grid-cols-1 gap-6 p-6 md:grid-cols-[220px_1fr]">
          <div class="flex flex-col gap-2">
            <div class="aspect-video overflow-hidden rounded-2xl border-2 border-ink bg-ink/5">
              <img
                v-if="entry.parse?.metadata.thumbnail && !entry.thumbnailLoadFailed"
                :src="normalizeThumbnailSrc(entry.parse.metadata.thumbnail)"
                :alt="entry.parse.metadata.title || 'thumbnail'"
                class="h-full w-full object-cover"
                referrerpolicy="no-referrer"
                loading="lazy"
                decoding="async"
                @error="onThumbnailError(entry)"
              />
              <div v-else class="flex h-full w-full items-center justify-center text-ink-mute">
                {{
                  entry.status === 'parsing'
                    ? '解析中…'
                    : entry.thumbnailLoadFailed
                      ? '封面加载失败'
                      : '无缩略图'
                }}
              </div>
            </div>
            <div class="flex flex-wrap gap-1 text-xs text-ink-mute">
              <span v-if="entry.parse?.metadata.duration" class="chip">
                ⏱ {{ formatDuration(entry.parse.metadata.duration) }}
              </span>
              <span v-if="entry.parse?.metadata.extractor" class="chip">
                🌐 {{ entry.parse.metadata.extractor }}
              </span>
            </div>
          </div>

          <div class="flex min-w-0 flex-col gap-3">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <div class="text-xs uppercase tracking-wide text-ink-mute">
                  {{ statusLabel(entry) }}
                </div>
                <h3 class="mt-1 truncate text-xl font-display">
                  {{ entry.parse?.metadata.title || entry.url }}
                </h3>
                <p class="mt-0.5 truncate text-xs text-ink-mute">
                  {{ entry.parse?.metadata.uploader || entry.url }}
                </p>
              </div>
              <button
                class="btn-ghost !px-2 !py-1"
                aria-label="移除任务"
                @click="removeEntry(entry)"
              >
                ✕
              </button>
            </div>

            <div v-if="entry.status === 'parsing'" class="flex items-center gap-2 text-ink-soft">
              <Spinner /> 正在解析视频信息…
            </div>

            <div v-else-if="entry.status === 'error'" class="rounded-2xl border-2 border-red-400 bg-red-50 p-3 text-sm text-red-800">
              <div class="font-semibold">{{ entry.error?.message || '失败' }}</div>
              <div v-if="entry.error?.hint" class="mt-1 text-red-700">{{ entry.error.hint }}</div>
              <div class="mt-2 flex gap-2">
                <button class="btn-secondary !py-1.5 !px-3 !text-sm" @click="retryEntry(entry)">
                  重试
                </button>
              </div>
            </div>

            <template v-else-if="entry.parse">
              <div class="grid grid-cols-1 gap-3 md:grid-cols-[1fr_minmax(220px,auto)]">
                <label class="block">
                  <span class="text-xs font-semibold uppercase text-ink-mute">格式 / 清晰度</span>
                  <select
                    v-model="entry.selectedFormat"
                    class="mt-1 w-full rounded-2xl border-2 border-ink bg-white px-4 py-2 text-sm shadow-sticker-sm focus:outline-none focus:ring-4 focus:ring-brand/30"
                  >
                    <option
                      v-for="fmt in entry.parse.formats"
                      :key="fmt.format_id"
                      :value="fmt"
                    >
                      {{ fmt.label
                      }}{{ fmt.filesize ? ` · ${formatBytes(fmt.filesize)}` : '' }}{{
                        fmt.is_recommended ? ' · 推荐' : ''
                      }}
                    </option>
                  </select>
                </label>
                <label class="block">
                  <span class="text-xs font-semibold uppercase text-ink-mute">下载模式</span>
                  <div class="mt-1 flex gap-1 rounded-full border-2 border-ink bg-white p-1 shadow-sticker-sm">
                    <button
                      v-for="m in modes"
                      :key="m.value"
                      type="button"
                      class="flex-1 rounded-full px-3 py-1 text-xs font-semibold transition-colors"
                      :class="entry.mode === m.value ? 'bg-brand text-white' : 'text-ink-soft hover:text-ink'"
                      :title="m.hint"
                      @click="entry.mode = m.value"
                    >
                      {{ m.label }}
                    </button>
                  </div>
                </label>
              </div>

              <div class="flex flex-wrap items-center gap-3">
                <button
                  class="btn-primary"
                  :disabled="['queued', 'downloading'].includes(entry.status)"
                  @click="startDownload(entry)"
                >
                  <span v-if="entry.status === 'downloading'">下载中…</span>
                  <span v-else-if="entry.status === 'queued'">排队中…</span>
                  <span v-else-if="entry.status === 'done'">重新下载</span>
                  <span v-else>开始下载</span>
                </button>
                <a
                  v-if="entry.status === 'done' && entry.downloadUrl"
                  :href="entry.downloadUrl"
                  class="btn-secondary"
                  target="_blank"
                  rel="noopener noreferrer"
                  :download="entry.fileName || ''"
                >
                  保存到本地
                </a>
                <span v-if="entry.selectedFormat" class="chip">
                  {{ entry.selectedFormat.kind === 'audio_only' ? '音频' : '视频' }}
                  · {{ entry.selectedFormat.ext.toUpperCase() }}
                </span>
              </div>

              <div
                v-if="entry.status === 'queued' || entry.status === 'downloading'"
                class="flex flex-col gap-1"
              >
                <div class="h-2 w-full overflow-hidden rounded-full bg-ink/10">
                  <div
                    class="h-full rounded-full bg-brand transition-[width] duration-500"
                    :style="{ width: `${Math.max(2, Math.round((entry.progress || 0) * 100))}%` }"
                  />
                </div>
                <div class="flex flex-wrap gap-3 text-xs text-ink-mute">
                  <span>{{ formatPercent(entry.progress) }}</span>
                  <span v-if="entry.speed">⚡ {{ entry.speed }}</span>
                  <span v-if="entry.eta">⏳ {{ formatEta(entry.eta) }}</span>
                </div>
              </div>

              <p v-if="entry.parse.subtitles.length" class="text-xs text-ink-mute">
                检测到 {{ entry.parse.subtitles.length }} 种字幕；可用下方「AI 学习助手」做摘要与导图。批量下载字幕合并仍为后续会员能力。
              </p>
              <VideoSummary
                :task-id="entry.parse.task_id"
                :subtitle-options="entry.parse.subtitles"
                :video-title="entry.parse.metadata.title ?? undefined"
              />
            </template>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="mt-10 card flex flex-col items-center gap-3 p-10 text-center">
      <div class="text-4xl">🎬</div>
      <p class="text-lg font-semibold">还没有任务</p>
      <p class="text-sm text-ink-soft">粘贴一条链接即可开始。批量模式可同时解析多条。</p>
    </div>
  </section>
</template>

