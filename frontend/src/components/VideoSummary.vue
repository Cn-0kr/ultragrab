<script setup lang="ts">
import { marked } from 'marked'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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

const props = withDefaults(
  defineProps<{
    taskId: string
    subtitleOptions: SubtitleLanguage[]
    videoTitle?: string
    /** 初始是否展开 AI 面板（单链接工作台默认展开） */
    defaultOpen?: boolean
    /** 挂载后自动跑一次摘要（批量解析时建议关闭） */
    autoSummarize?: boolean
    /** 贴入右侧分栏时略微收紧外框样式 */
    embedded?: boolean
  }>(),
  {
    defaultOpen: false,
    autoSummarize: false,
    embedded: false,
  },
)

type TabId = 'summary' | 'subs' | 'mind' | 'chat'

const panelOpen = ref(props.defaultOpen)
const activeTab = ref<TabId>('summary')

const cues = ref<TranscriptCue[]>([])
const transcriptLoading = ref(false)
const cueFilter = ref('')

const summaryErr = ref<string | null>(null)
const subsErr = ref<string | null>(null)
const mindErr = ref<string | null>(null)
const chatErr = ref<string | null>(null)

const selectedLangCodes = ref<string[]>([])
const subtitleLangParam = computed(() =>
  selectedLangCodes.value.length ? [...selectedLangCodes.value] : undefined,
)

/* ── Language selector: split into primary vs auto-translated ── */

const pinnedCodes = new Set(['zh-Hans', 'zh-Hant', 'zh', 'zh-CN', 'zh-TW'])

const primaryLangs = computed(() =>
  props.subtitleOptions.filter((s) => !s.is_automatic || pinnedCodes.has(s.code)),
)
const autoLangs = computed(() =>
  props.subtitleOptions.filter((s) => s.is_automatic && !pinnedCodes.has(s.code)),
)
const showMoreLangs = ref(false)
const langSearch = ref('')
const filteredAutoLangs = computed(() => {
  const q = langSearch.value.trim().toLowerCase()
  if (!q) return autoLangs.value
  return autoLangs.value.filter(
    (s) =>
      (s.name || '').toLowerCase().includes(q) ||
      s.code.toLowerCase().includes(q),
  )
})

const summaryText = ref('')
const summaryRunning = ref(false)
const summaryAbort = ref<AbortController | null>(null)

const mindmapCode = ref('')
const mindLoading = ref(false)

const chatMessages = ref<ChatMessage[]>([])
const chatInput = ref('')
const chatRunning = ref(false)
const chatAbort = ref<AbortController | null>(null)

const mindmapFullscreen = ref(false)
const fullscreenMermaidHost = ref<HTMLElement | null>(null)

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

function formatSrtTs(ms: number): string {
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mil = ms % 1000
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(mil).padStart(3, '0')}`
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

async function ensureTranscript(): Promise<string | null> {
  if (cues.value.length) return null
  transcriptLoading.value = true
  try {
    const res = await postTranscript(props.taskId, subtitleLangParam.value)
    cues.value = res.cues
    return null
  } catch (e) {
    return formatCaught(e)
  } finally {
    transcriptLoading.value = false
  }
}

watch(panelOpen, async (open) => {
  if (open && activeTab.value === 'subs') {
    const err = await ensureTranscript()
    if (err) subsErr.value = err
  }
})

watch(activeTab, async (tab) => {
  if (!panelOpen.value) return
  if (tab === 'subs') {
    const err = await ensureTranscript()
    if (err) subsErr.value = err
  }
})

async function runSummary() {
  summaryAbort.value?.abort()
  summaryAbort.value = new AbortController()
  summaryRunning.value = true
  summaryText.value = ''
  summaryErr.value = null
  try {
    const err = await ensureTranscript()
    if (err) {
      summaryErr.value = err
      return
    }
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
    summaryErr.value = formatCaught(e)
  } finally {
    summaryRunning.value = false
    summaryAbort.value = null
  }
}

const autoSummaryForTask = ref<string | null>(null)
watch(
  () => props.taskId,
  (id) => {
    if (!props.autoSummarize || !id) return
    if (autoSummaryForTask.value === id) return
    autoSummaryForTask.value = id
    panelOpen.value = true
    void runSummary()
  },
  { immediate: true },
)

function stopSummary() {
  summaryAbort.value?.abort()
}

const mermaidHost = ref<HTMLElement | null>(null)
let renderCounter = 0

function stripMermaidFences(raw: string): string {
  let code = raw.trim()
  code = code.replace(/^```(?:mermaid)?\s*/i, '').replace(/```\s*$/, '').trim()
  return code
}

/** First non-empty line decides diagram kind (LLM有时仍输出 flowchart）。 */
function mermaidFirstDirective(code: string): 'flowchart' | 'mindmap' | 'other' {
  for (const line of code.split('\n')) {
    const t = line.trim()
    if (!t) continue
    if (/^(flowchart|graph)\s/i.test(t)) return 'flowchart'
    if (/^mindmap\b/i.test(t)) return 'mindmap'
    return 'other'
  }
  return 'other'
}

function sanitizeFlowchart(code: string): string {
  const lines = stripMermaidFences(code).split('\n')
  const out: string[] = []
  for (const line of lines) {
    if (/^\s*classDef\b/.test(line) || /^\s*class\b/.test(line)) continue
    out.push(line)
  }
  return out.join('\n').trim()
}

function firstNonEmptyLine(s: string): string {
  return s.split('\n').find((l) => l.trim())?.trim() || ''
}

function sanitizeMindmap(raw: string): string {
  let code = stripMermaidFences(raw)
  if (mermaidFirstDirective(code) === 'flowchart') {
    return sanitizeFlowchart(code)
  }
  if (!/^mindmap\b/i.test(firstNonEmptyLine(code))) {
    code = `mindmap\n${code}`
  }
  const lines = code.split('\n')
  const cleaned: string[] = []
  for (const line of lines) {
    if (/^\s*classDef\b/.test(line) || /^\s*class\b/.test(line)) continue
    if (/-->/.test(line)) continue
    const trimmedEnd = line.trimEnd()
    if (!trimmedEnd || /^mindmap\b/i.test(trimmedEnd.trim())) continue
    const indent = line.match(/^(\s*)/)?.[1] || ''
    const content = trimmedEnd.slice(indent.length).replace(/^:::.*$/, '').trim()
    if (!content) continue
    cleaned.push(indent + content)
  }
  if (!cleaned.length) {
    return 'mindmap\n  空'
  }
  cleaned.unshift('mindmap')
  return cleaned.join('\n')
}

function prepareMermaidForRender(raw: string): { kind: 'flowchart' | 'mindmap'; code: string } {
  const stripped = stripMermaidFences(raw)
  const dir = mermaidFirstDirective(stripped)
  if (dir === 'flowchart') {
    return { kind: 'flowchart', code: sanitizeFlowchart(stripped) }
  }
  return { kind: 'mindmap', code: sanitizeMindmap(stripped) }
}

async function renderMermaid() {
  if (!mindmapCode.value.trim() || !mermaidHost.value) return
  const el = mermaidHost.value
  el.innerHTML = ''
  renderCounter++

  const { kind, code } = prepareMermaidForRender(mindmapCode.value)
  const pre = document.createElement('pre')
  pre.className = 'mermaid'
  pre.id = `mm-${Date.now()}-${renderCounter}`
  pre.textContent = code
  el.appendChild(pre)
  try {
    const mod = await import('mermaid')
    mod.default.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'base',
      deterministicIds: false,
      themeVariables: {
        fontFamily: '"Inter", ui-sans-serif, system-ui, sans-serif',
        primaryColor: '#DFF7F2',
        primaryTextColor: '#0F172A',
        secondaryColor: '#FFF9EF',
        tertiaryColor: '#B8E8E0',
        lineColor: '#0F172A',
        textColor: '#0F172A',
      },
    })
    await mod.default.run({ nodes: [pre] })
    mindErr.value = null
  } catch {
    el.innerHTML = ''
    renderCounter++
    const fallbackCode =
      kind === 'mindmap'
        ? convertMindmapToFlowchart(code)
        : repairFlowchartForFallback(code)
    const pre2 = document.createElement('pre')
    pre2.className = 'mermaid'
    pre2.id = `mm-${Date.now()}-${renderCounter}`
    pre2.textContent = fallbackCode
    el.appendChild(pre2)
    try {
      const mod = await import('mermaid')
      await mod.default.run({ nodes: [pre2] })
      mindErr.value = null
    } catch (err2) {
      mindErr.value =
        err2 instanceof Error ? `导图渲染失败：${err2.message}` : '导图渲染失败'
    }
  }
}

/** flowchart 首渲失败时原样再试（已 sanitize）；仍空则给占位节点 */
function repairFlowchartForFallback(code: string): string {
  const c = sanitizeFlowchart(code)
  return c.trim() ? c : 'flowchart TD\n  _e["渲染失败，请重试生成"]'
}

function escapeFlowchartLabel(label: string): string {
  return label.replace(/"/g, "'").replace(/\]/g, '〕').replace(/\[/g, '〔')
}

function convertMindmapToFlowchart(mindmapCode: string): string {
  const lines = mindmapCode.split('\n').filter((l) => {
    const t = l.trim()
    if (!t) return false
    if (t === 'mindmap') return false
    if (/^(flowchart|graph)\b/i.test(t)) return false
    return true
  })
  if (!lines.length) {
    return 'flowchart TD\n  _empty["导图节点为空，请重新生成思维导图"]'
  }

  const nodes: { id: string; label: string; indent: number }[] = []
  let idCounter = 0
  for (const line of lines) {
    const indent = (line.match(/^(\s*)/)?.[1] || '').length
    let label = line.trim()
    label = label
      .replace(/^\(\((.+)\)\)$/, '$1')
      .replace(/^\[(.+)\]$/, '$1')
      .replace(/^\((.+)\)$/, '$1')
      .replace(/^root\(\((.+)\)\)$/, '$1')
    nodes.push({ id: `N${idCounter++}`, label, indent })
  }

  const edges: string[] = []
  for (let i = 1; i < nodes.length; i++) {
    let parent = -1
    for (let j = i - 1; j >= 0; j--) {
      if (nodes[j].indent < nodes[i].indent) {
        parent = j
        break
      }
    }
    if (parent >= 0) {
      edges.push(`  ${nodes[parent].id} --> ${nodes[i].id}`)
    }
  }

  const defs = nodes.map((n) => `  ${n.id}["${escapeFlowchartLabel(n.label)}"]`)
  const body = [defs.join('\n'), edges.join('\n')].filter(Boolean).join('\n')
  return `flowchart TD\n${body}`
}

async function runMindmap() {
  mindLoading.value = true
  mindErr.value = null
  mindmapCode.value = ''
  lastRenderedCode = ''
  try {
    const err = await ensureTranscript()
    if (err) {
      mindErr.value = err
      return
    }
    const res = await postMindmap(props.taskId, subtitleLangParam.value)
    mindmapCode.value = res.mermaid
    await nextTick()
    await renderMermaid()
  } catch (e) {
    mindErr.value = formatCaught(e)
  } finally {
    mindLoading.value = false
  }
}

let lastRenderedCode = ''

watch([mindmapCode, activeTab], async () => {
  if (activeTab.value === 'mind' && mindmapCode.value && mindmapCode.value !== lastRenderedCode) {
    lastRenderedCode = mindmapCode.value
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
  chatErr.value = null
  const assistant: ChatMessage = { role: 'assistant', content: '' }
  chatMessages.value.push(assistant)
  try {
    const err = await ensureTranscript()
    if (err) {
      chatMessages.value.pop()
      chatMessages.value.pop()
      chatErr.value = err
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

/* ── Mindmap fullscreen ── */

function toggleFullscreen() {
  mindmapFullscreen.value = !mindmapFullscreen.value
}

watch(mindmapFullscreen, async (open) => {
  if (open) {
    await nextTick()
    if (mermaidHost.value && fullscreenMermaidHost.value) {
      const svg = mermaidHost.value.querySelector('svg')
      if (svg) {
        fullscreenMermaidHost.value.innerHTML = ''
        const clone = svg.cloneNode(true) as SVGSVGElement
        clone.removeAttribute('width')
        clone.removeAttribute('height')
        clone.removeAttribute('style')
        clone.style.maxWidth = '100%'
        clone.style.maxHeight = 'calc(100vh - 6rem)'
        clone.style.width = 'auto'
        clone.style.height = 'auto'
        fullscreenMermaidHost.value.appendChild(clone)
      }
    }
  }
})

function onEscKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && mindmapFullscreen.value) {
    mindmapFullscreen.value = false
  }
}

onMounted(() => document.addEventListener('keydown', onEscKey))
onUnmounted(() => document.removeEventListener('keydown', onEscKey))

/* ── Mindmap export: PNG + SVG ── */

function prepareSvgForExport(): SVGSVGElement | null {
  const svg = mermaidHost.value?.querySelector('svg')
  if (!svg) return null
  const clone = svg.cloneNode(true) as SVGSVGElement
  const bbox = svg.getBBox()
  const w = Math.ceil(bbox.width + bbox.x * 2) || svg.clientWidth || 800
  const h = Math.ceil(bbox.height + bbox.y * 2) || svg.clientHeight || 600
  clone.setAttribute('width', String(w))
  clone.setAttribute('height', String(h))
  if (!clone.getAttribute('xmlns')) {
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  }
  return clone
}

function replaceForeignObjects(svgEl: SVGSVGElement) {
  const fos = svgEl.querySelectorAll('foreignObject')
  fos.forEach((fo) => {
    const textContent = fo.textContent?.trim() || ''
    const x = fo.getAttribute('x') || '0'
    const y = fo.getAttribute('y') || '0'
    const w = parseFloat(fo.getAttribute('width') || '100')
    const h = parseFloat(fo.getAttribute('height') || '20')
    const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    textEl.setAttribute('x', String(parseFloat(x) + w / 2))
    textEl.setAttribute('y', String(parseFloat(y) + h / 2))
    textEl.setAttribute('text-anchor', 'middle')
    textEl.setAttribute('dominant-baseline', 'central')
    textEl.setAttribute('font-size', '14')
    textEl.setAttribute('font-family', 'sans-serif')
    textEl.textContent = textContent
    fo.parentNode?.replaceChild(textEl, fo)
  })
}

function downloadMindmapPng() {
  const clone = prepareSvgForExport()
  if (!clone) return
  replaceForeignObjects(clone)
  const w = Number(clone.getAttribute('width'))
  const h = Number(clone.getAttribute('height'))
  const svgData = new XMLSerializer().serializeToString(clone)
  const dataUrl = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)))

  const dpr = 2
  const img = new Image()
  img.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = w * dpr
    canvas.height = h * dpr
    const ctx = canvas.getContext('2d')!
    ctx.scale(dpr, dpr)
    ctx.drawImage(img, 0, 0, w, h)
    canvas.toBlob((blob) => {
      if (!blob) return
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${props.videoTitle || 'mindmap'}.png`
      a.click()
      URL.revokeObjectURL(a.href)
    }, 'image/png')
  }
  img.src = dataUrl
}

function downloadMindmapSvg() {
  const clone = prepareSvgForExport()
  if (!clone) return
  const svgData = new XMLSerializer().serializeToString(clone)
  const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.videoTitle || 'mindmap'}.svg`
  a.click()
  URL.revokeObjectURL(a.href)
}

/* ── Subtitle export: SRT + TXT ── */

function downloadSubtitleSrt() {
  if (!cues.value.length) return
  const srt = cues.value
    .map(
      (c, i) =>
        `${i + 1}\n${formatSrtTs(c.start_ms)} --> ${formatSrtTs(c.end_ms)}\n${c.text}`,
    )
    .join('\n\n')
  const blob = new Blob([srt], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.videoTitle || 'subtitle'}.srt`
  a.click()
  URL.revokeObjectURL(a.href)
}

function downloadSubtitleTxt() {
  if (!cues.value.length) return
  const txt = cues.value.map((c) => c.text).join('\n')
  const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.videoTitle || 'subtitle'}.txt`
  a.click()
  URL.revokeObjectURL(a.href)
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
    :class="[
      'video-ai-panel rounded-2xl border-2 p-4 font-sans text-ink antialiased shadow-sticker-sm',
      props.embedded
        ? 'border-ink/15 bg-white/95'
        : 'mt-4 border-dashed border-ink/25 bg-brand-soft/40',
    ]"
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
      基于<strong class="font-semibold text-ink">字幕 / 语音转写</strong>生成摘要、导图与问答。支持 yt-dlp
      可解析的站点（含 <strong class="font-semibold text-ink">YouTube、Bilibili</strong>
      等）；无平台字幕时将自动尝试
      <strong class="font-semibold text-ink">ASR 语音转写</strong>提取文本。
    </p>

    <!-- ── Language selector: primary languages shown, auto-translated collapsed ── -->
    <div v-if="subtitleOptions.length" class="mt-3 flex flex-col gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs font-semibold uppercase text-ink-mute">字幕语言</span>
        <button
          v-for="s in primaryLangs"
          :key="s.code"
          type="button"
          class="chip cursor-pointer transition-colors"
          :class="selectedLangCodes.includes(s.code) ? 'border-brand bg-brand text-white' : ''"
          @click="toggleLang(s.code)"
        >
          {{ s.name || s.code }}
        </button>
        <span v-if="!primaryLangs.length" class="text-xs text-ink-mute">
          （未选则自动偏好中文/英文）
        </span>
      </div>
      <div v-if="autoLangs.length">
        <button
          type="button"
          class="text-xs text-brand-dark underline underline-offset-2 hover:text-brand"
          @click="showMoreLangs = !showMoreLangs"
        >
          {{ showMoreLangs ? '收起自动翻译' : `更多自动翻译字幕（${autoLangs.length} 种）▸` }}
        </button>
        <div v-if="showMoreLangs" class="mt-2 flex flex-col gap-2">
          <input
            v-model="langSearch"
            type="search"
            placeholder="搜索语言…"
            class="w-full max-w-xs rounded-full border-2 border-ink bg-white px-3 py-1.5 text-xs shadow-sticker-sm focus:outline-none focus:ring-4 focus:ring-brand/30"
          />
          <div class="flex max-h-36 flex-wrap gap-1 overflow-auto">
            <button
              v-for="s in filteredAutoLangs"
              :key="s.code"
              type="button"
              class="chip cursor-pointer text-[11px] transition-colors"
              :class="selectedLangCodes.includes(s.code) ? 'border-brand bg-brand text-white' : ''"
              @click="toggleLang(s.code)"
            >
              {{ s.name || s.code }}
            </button>
            <span v-if="!filteredAutoLangs.length" class="text-xs text-ink-mute">无匹配结果</span>
          </div>
        </div>
      </div>
    </div>
    <p v-else class="mt-2 text-xs text-ink-mute">
      当前解析结果未列出字幕轨道，将自动使用 ASR 语音转写。
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

      <!-- ── Summary Tab ── -->
      <div v-if="activeTab === 'summary'" class="flex flex-col gap-3">
        <div
          v-if="summaryErr"
          class="rounded-2xl border-2 border-red-400 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {{ summaryErr }}
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn-primary !py-2 !text-sm"
            :disabled="summaryRunning"
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
        <p v-else-if="summaryRunning && transcriptLoading" class="text-sm text-ink-soft">
          正在获取字幕或进行语音转写（长视频可能需数分钟），完成后将自动生成摘要…
        </p>
        <p v-else-if="summaryRunning" class="text-sm text-ink-soft">
          正在流式生成摘要，请稍候…
        </p>
        <p v-else class="text-sm text-ink-soft">生成后可在此查看 Markdown 结构化的要点提纲。</p>
      </div>

      <!-- ── Subs Tab ── -->
      <div v-else-if="activeTab === 'subs'" class="flex flex-col gap-3">
        <div
          v-if="subsErr"
          class="rounded-2xl border-2 border-red-400 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {{ subsErr }}
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="transcriptLoading"
            @click="ensureTranscript().then(e => { if (e) subsErr = e })"
          >
            {{ transcriptLoading ? '加载字幕…' : '刷新字幕' }}
          </button>
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="!cues.length"
            @click="downloadSubtitleSrt"
          >
            下载 SRT
          </button>
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="!cues.length"
            @click="downloadSubtitleTxt"
          >
            下载 TXT
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

      <!-- ── Mind Tab ── -->
      <div v-else-if="activeTab === 'mind'" class="flex flex-col gap-3">
        <div
          v-if="mindErr"
          class="rounded-2xl border-2 border-red-400 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {{ mindErr }}
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn-primary !py-2 !text-sm"
            :disabled="mindLoading"
            @click="runMindmap"
          >
            {{ mindLoading ? '生成中…' : '生成思维导图' }}
          </button>
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="!mermaidHost?.querySelector('svg')"
            @click="toggleFullscreen"
          >
            全屏查看
          </button>
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="!mermaidHost?.querySelector('svg')"
            @click="downloadMindmapPng"
          >
            下载 PNG
          </button>
          <button
            type="button"
            class="btn-secondary !py-2 !text-sm"
            :disabled="!mermaidHost?.querySelector('svg')"
            @click="downloadMindmapSvg"
          >
            下载 SVG
          </button>
        </div>
        <div
          ref="mermaidHost"
          class="mindmap-host min-h-[160px] overflow-x-auto rounded-2xl border-2 border-ink bg-white p-4 font-sans text-sm shadow-sticker-sm [&_svg]:max-w-none"
        />
      </div>

      <!-- ── Chat Tab ── -->
      <div v-else class="flex flex-col gap-3">
        <div
          v-if="chatErr"
          class="rounded-2xl border-2 border-red-400 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {{ chatErr }}
        </div>
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
              :disabled="chatRunning"
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

  <!-- ── Mindmap fullscreen modal (true fullscreen) ── -->
  <Teleport to="body">
    <div
      v-if="mindmapFullscreen"
      class="fixed inset-0 z-50 flex flex-col bg-white"
    >
      <div
        class="flex items-center justify-between border-b-2 border-ink/10 px-6 py-3"
      >
        <span class="font-display text-lg text-ink">思维导图预览</span>
        <button
          type="button"
          class="rounded-full border-2 border-ink bg-white px-4 py-1.5 text-sm font-semibold text-ink shadow-sticker-sm transition-colors hover:bg-red-50"
          @click="mindmapFullscreen = false"
        >
          ✕ 关闭
        </button>
      </div>
      <div
        ref="fullscreenMermaidHost"
        class="mindmap-host flex flex-1 items-center justify-center overflow-auto p-8 [&_svg]:max-w-none"
      />
    </div>
  </Teleport>
</template>
