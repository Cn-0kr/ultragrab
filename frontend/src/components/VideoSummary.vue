<script setup lang="ts">
import { marked } from 'marked'
import { computed, nextTick, ref, watch } from 'vue'
import type { SubtitleLanguage } from '../api/types'
import {
  postMindmap,
  postTranscript,
  streamChat,
  streamSummarize,
  VideoAiError,
  type ChatMessage,
  type TranscriptCue,
} from '../api/videoAi'

const props = defineProps<{
  taskId: string
  subtitleOptions: SubtitleLanguage[]
}>()

type TabId = 'summary' | 'subs' | 'mind' | 'chat'

const panelOpen = ref(false)
const activeTab = ref<TabId>('summary')

const cues = ref<TranscriptCue[]>([])
const transcriptLoading = ref(false)
const transcriptErr = ref<string | null>(null)
const cueFilter = ref('')

const selectedLangCodes = ref<string[]>([])
const subtitleLangParam = computed(() =>
  selectedLangCodes.value.length ? [...selectedLangCodes.value] : undefined,
)

const summaryText = ref('')
const summaryRunning = ref(false)
const summaryAbort = ref<AbortController | null>(null)

const mindmapCode = ref('')
const mindLoading = ref(false)

const chatMessages = ref<ChatMessage[]>([])
const chatInput = ref('')
const chatRunning = ref(false)
const chatAbort = ref<AbortController | null>(null)

const filteredCues = computed(() => {
  const q = cueFilter.value.trim().toLowerCase()
  if (!q) return cues.value
  return cues.value.filter((c) => c.text.toLowerCase().includes(q))
})

function formatTs(ms: number): string {
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

/** Avoid `[object Object]` when thrown values are plain objects. */
function formatCaught(err: unknown): string {
  if (err instanceof VideoAiError) {
    return err.hint ? `${err.message} · ${err.hint}` : err.message
  }
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  if (typeof err === 'number' || typeof err === 'boolean') return String(err)
  try {
    return JSON.stringify(err)
  } catch {
    return '未知错误'
  }
}

function summaryHtml(md: string): string {
  return marked.parse(md, { async: false, breaks: true }) as string
}

async function ensureTranscript(): Promise<boolean> {
  if (cues.value.length) return true
  transcriptLoading.value = true
  transcriptErr.value = null
  try {
    const res = await postTranscript(props.taskId, subtitleLangParam.value)
    cues.value = res.cues
    return true
  } catch (e) {
    transcriptErr.value = formatCaught(e)
    return false
  } finally {
    transcriptLoading.value = false
  }
}

watch(panelOpen, async (open) => {
  if (open && activeTab.value === 'subs') {
    await ensureTranscript()
  }
})

watch(activeTab, async (tab) => {
  if (!panelOpen.value) return
  if (tab === 'subs') await ensureTranscript()
})

async function runSummary() {
  summaryAbort.value?.abort()
  summaryAbort.value = new AbortController()
  summaryRunning.value = true
  summaryText.value = ''
  transcriptErr.value = null
  try {
    const ok = await ensureTranscript()
    if (!ok) return
    await streamSummarize(
      props.taskId,
      subtitleLangParam.value,
      (_full, _d) => {
        summaryText.value = _full
      },
      summaryAbort.value.signal,
    )
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    transcriptErr.value = formatCaught(e)
  } finally {
    summaryRunning.value = false
    summaryAbort.value = null
  }
}

function stopSummary() {
  summaryAbort.value?.abort()
}

const mermaidHost = ref<HTMLElement | null>(null)

async function renderMermaid() {
  if (!mindmapCode.value.trim() || !mermaidHost.value) return
  const el = mermaidHost.value
  el.innerHTML = ''
  const pre = document.createElement('pre')
  pre.className = 'mermaid'
  pre.textContent = mindmapCode.value
  el.appendChild(pre)
  try {
    const mod = await import('mermaid')
    mod.default.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      themeVariables: {
        fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
        primaryColor: '#DFF7F2',
        primaryTextColor: '#0F172A',
        secondaryColor: '#FFF9EF',
        tertiaryColor: '#ffffff',
        lineColor: '#0F172A',
        textColor: '#0F172A',
      },
    })
    await mod.default.run({ nodes: [pre] })
    transcriptErr.value = null
  } catch (err) {
    transcriptErr.value =
      err instanceof Error ? `导图渲染失败：${err.message}` : '导图渲染失败'
    console.warn(err)
  }
}

async function runMindmap() {
  mindLoading.value = true
  transcriptErr.value = null
  mindmapCode.value = ''
  try {
    const ok = await ensureTranscript()
    if (!ok) return
    const res = await postMindmap(props.taskId, subtitleLangParam.value)
    mindmapCode.value = res.mermaid
    await nextTick()
    await renderMermaid()
  } catch (e) {
    transcriptErr.value = formatCaught(e)
  } finally {
    mindLoading.value = false
  }
}

watch([mindmapCode, activeTab], async () => {
  if (activeTab.value === 'mind' && mindmapCode.value) {
    await nextTick()
    await renderMermaid()
  }
})

async function sendChat() {
  const text = chatInput.value.trim()
  if (!text || chatRunning.value) return
  chatAbort.value?.abort()
  chatAbort.value = new AbortController()
  chatMessages.value.push({ role: 'user', content: text })
  chatInput.value = ''
  chatRunning.value = true
  transcriptErr.value = null
  const assistant: ChatMessage = { role: 'assistant', content: '' }
  chatMessages.value.push(assistant)
  try {
    const ok = await ensureTranscript()
    if (!ok) {
      chatMessages.value.pop()
      chatMessages.value.pop()
      return
    }
    const history = chatMessages.value.slice(0, -1)
    await streamChat(
      props.taskId,
      history,
      subtitleLangParam.value,
      (full) => {
        assistant.content = full
      },
      chatAbort.value.signal,
    )
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    assistant.content = `错误：${formatCaught(e)}`
  } finally {
    chatRunning.value = false
    chatAbort.value = null
  }
}

function stopChat() {
  chatAbort.value?.abort()
}

function toggleLang(code: string) {
  const set = new Set(selectedLangCodes.value)
  if (set.has(code)) set.delete(code)
  else set.add(code)
  selectedLangCodes.value = [...set]
  cues.value = []
}
</script>

<style scoped>
.markdown-summary :deep(h2) {
  @apply mt-4 border-b border-ink/15 pb-1 font-display text-lg text-ink;
}
.markdown-summary :deep(p) {
  @apply mt-2 text-ink-soft;
}
.markdown-summary :deep(ul) {
  @apply mt-2 list-disc pl-5 text-ink-soft;
}
.markdown-summary :deep(li) {
  @apply mt-1;
}
.markdown-summary :deep(strong) {
  @apply font-semibold text-ink;
}
</style>

<template>
  <div
    class="video-ai-panel mt-4 rounded-2xl border-2 border-dashed border-ink/25 bg-brand-soft/40 p-4 font-sans text-ink antialiased shadow-sticker-sm"
  >
    <button
      type="button"
      class="flex w-full items-center justify-between gap-2 text-left font-display text-lg text-ink"
      @click="panelOpen = !panelOpen"
    >
      <span>✨ AI 学习助手</span>
      <span class="text-sm font-semibold text-brand-dark">{{ panelOpen ? '收起' : '展开' }}</span>
    </button>
    <p class="mt-1 text-xs text-ink-soft">
      基于<strong class="font-semibold text-ink">平台字幕</strong>生成摘要、导图与问答（需服务端
      DEEPSEEK_API_KEY）。支持 yt-dlp
      可解析的站点（含 <strong class="font-semibold text-ink">YouTube、Bilibili</strong>
      等）；<strong class="font-semibold text-ink">抖音</strong
      >等平台若解析结果中<strong class="font-semibold text-ink">无字幕轨道</strong
      >则无法使用本节功能。
    </p>

    <div v-if="subtitleOptions.length" class="mt-3 flex flex-wrap gap-2">
      <span class="text-xs font-semibold uppercase text-ink-mute">字幕语言</span>
      <button
        v-for="s in subtitleOptions"
        :key="s.code"
        type="button"
        class="chip cursor-pointer transition-colors"
        :class="selectedLangCodes.includes(s.code) ? 'border-brand bg-brand text-white' : ''"
        @click="toggleLang(s.code)"
      >
        {{ s.name || s.code }}{{ s.is_automatic ? ' · 自动' : '' }}
      </button>
      <span class="text-xs text-ink-mute">（未选则自动偏好中文/英文）</span>
    </div>
    <p v-else class="mt-2 text-xs font-semibold text-amber-800">
      当前解析结果未列出字幕轨道：AI 功能可能不可用。
    </p>

    <div v-if="panelOpen" class="mt-4 flex flex-col gap-4">
      <div class="flex flex-wrap gap-2 rounded-full border-2 border-ink bg-white p-1 shadow-sticker-sm">
        <button
          v-for="t in [
            { id: 'summary' as const, label: '总结' },
            { id: 'subs' as const, label: '字幕' },
            { id: 'mind' as const, label: '导图' },
            { id: 'chat' as const, label: '问答' },
          ]"
          :key="t.id"
          type="button"
          class="rounded-full px-4 py-2 text-xs font-semibold transition-colors md:text-sm"
          :class="activeTab === t.id ? 'bg-brand text-white' : 'text-ink-soft hover:text-ink'"
          @click="activeTab = t.id"
        >
          {{ t.label }}
        </button>
      </div>

      <div
        v-if="transcriptErr"
        class="rounded-2xl border-2 border-red-400 bg-red-50 px-4 py-3 text-sm text-red-800"
      >
        {{ transcriptErr }}
      </div>

      <div v-if="activeTab === 'summary'" class="flex flex-col gap-3">
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn-primary !py-2 !text-sm"
            :disabled="summaryRunning || !subtitleOptions.length"
            @click="runSummary"
          >
            {{ summaryRunning ? '生成中…' : '生成摘要' }}
          </button>
          <button
            v-if="summaryRunning"
            type="button"
            class="btn-secondary !py-2 !text-sm"
            @click="stopSummary"
          >
            停止
          </button>
        </div>
        <div
          v-if="summaryText"
          class="markdown-summary max-w-none space-y-2 rounded-2xl border-2 border-ink bg-white p-4 text-sm leading-relaxed text-ink shadow-sticker-sm"
          v-html="summaryHtml(summaryText)"
        />
        <p v-else class="text-sm text-ink-soft">生成后可在此查看 Markdown 结构化的要点提纲。</p>
      </div>

      <div v-else-if="activeTab === 'subs'" class="flex flex-col gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="transcriptLoading"
            @click="ensureTranscript"
          >
            {{ transcriptLoading ? '加载字幕…' : '刷新字幕' }}
          </button>
          <input
            v-model="cueFilter"
            type="search"
            placeholder="筛选字幕…"
            class="min-w-[140px] flex-1 rounded-full border-2 border-ink bg-white px-4 py-2 text-sm shadow-sticker-sm focus:outline-none focus:ring-4 focus:ring-brand/30"
          />
        </div>
        <div
          class="max-h-72 overflow-auto rounded-2xl border-2 border-ink bg-white p-3 text-sm shadow-sticker-sm"
        >
          <ul class="space-y-2">
            <li
              v-for="(c, i) in filteredCues"
              :key="i"
              class="rounded-xl border border-ink/10 bg-cream/80 px-3 py-2"
            >
              <span class="mr-2 font-mono text-xs text-brand-dark">{{ formatTs(c.start_ms) }}</span>
              <span class="text-ink">{{ c.text }}</span>
            </li>
          </ul>
          <p v-if="!transcriptLoading && !filteredCues.length" class="text-ink-mute">暂无字幕条目。</p>
        </div>
      </div>

      <div v-else-if="activeTab === 'mind'" class="flex flex-col gap-3">
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn-primary !py-2 !text-sm"
            :disabled="mindLoading || !subtitleOptions.length"
            @click="runMindmap"
          >
            {{ mindLoading ? '生成中…' : '生成思维导图' }}
          </button>
        </div>
        <div
          ref="mermaidHost"
          class="mindmap-host min-h-[160px] overflow-x-auto rounded-2xl border-2 border-ink bg-white p-4 font-sans text-sm shadow-sticker-sm [&_svg]:max-w-none"
        />
      </div>

      <div v-else class="flex flex-col gap-3">
        <div
          class="flex max-h-72 flex-col gap-2 overflow-auto rounded-2xl border-2 border-ink bg-white p-3 shadow-sticker-sm"
        >
          <div v-for="(m, i) in chatMessages" :key="i" class="text-sm">
            <span class="font-semibold text-brand-dark">{{
              m.role === 'user' ? '你' : '助手'
            }}</span>
            <p class="mt-1 whitespace-pre-wrap text-ink">{{ m.content }}</p>
          </div>
        </div>
        <div class="flex flex-col gap-2 md:flex-row md:items-end">
          <textarea
            v-model="chatInput"
            rows="2"
            placeholder="基于本片字幕提问…"
            class="flex-1 rounded-[22px] border-2 border-ink bg-white px-4 py-3 text-sm shadow-sticker-sm focus:outline-none focus:ring-4 focus:ring-brand/30"
          />
          <div class="flex gap-2">
            <button
              type="button"
              class="btn-primary !py-2 !text-sm"
              :disabled="chatRunning || !subtitleOptions.length"
              @click="sendChat"
            >
              {{ chatRunning ? '回复中…' : '发送' }}
            </button>
            <button
              v-if="chatRunning"
              type="button"
              class="btn-secondary !py-2 !text-sm"
              @click="stopChat"
            >
              停止
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
