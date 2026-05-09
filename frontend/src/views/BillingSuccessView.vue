<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError, getToken } from '@/api/client'
import { useAuth } from '@/composables/useAuth'

const route = useRoute()
const { user, refresh } = useAuth()

const sessionId = ref<string | null>(null)
const statusText = ref('正在确认支付结果…')
const errorText = ref<string | null>(null)
const timedOut = ref(false)
const succeeded = ref(false)
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

const POLL_MS = 2000
const TIMEOUT_MS = 120_000

onMounted(async () => {
  document.title = '支付完成 - UltraGrab'
  const sid = route.query.session_id
  sessionId.value = typeof sid === 'string' ? sid : null

  if (!getToken()) {
    errorText.value = '请先登录后再查看订阅状态。'
    statusText.value = ''
    return
  }

  const started = Date.now()
  const tick = async () => {
    try {
      await refresh()
      if (user.value?.has_active_subscription) {
        succeeded.value = true
        statusText.value = '支付成功，您已是 Pro 会员。'
        stopPoll()
        return
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'unauthorized') {
        errorText.value = '登录已失效，请重新登录。'
        stopPoll()
        return
      }
    }
    if (Date.now() - started > TIMEOUT_MS) {
      timedOut.value = true
      statusText.value =
        '仍未同步到 Pro 状态。常见原因：Stripe Webhook 签名校验失败（后端对事件返回 400），订阅未写入数据库。'
      stopPoll()
    }
  }

  await tick()
  if (!errorText.value && !user.value?.has_active_subscription) {
    pollTimer.value = setInterval(() => void tick(), POLL_MS)
  }
})

function stopPoll() {
  if (pollTimer.value != null) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

onUnmounted(stopPoll)
</script>

<template>
  <div class="mx-auto max-w-lg px-4 py-16 md:py-24">
    <div class="card p-8 text-center">
      <h1 class="text-2xl font-display">感谢支持</h1>
      <p v-if="statusText" class="mt-3 text-ink-soft">{{ statusText }}</p>
      <div
        v-if="timedOut && sessionId && !succeeded"
        class="mt-4 rounded-xl border-2 border-amber-200 bg-amber-50/80 p-4 text-left text-sm text-ink-soft"
      >
        <p class="font-semibold text-ink">若长时间停在本页，请自检：</p>
        <ul class="mt-2 list-inside list-disc space-y-1.5">
          <li>
            是否运行
            <code class="rounded bg-white px-1 py-0.5 font-mono text-xs text-ink">stripe listen --forward-to http://127.0.0.1:8000/api/stripe/webhook</code>
          </li>
          <li>终端里打印的 <code class="font-mono text-xs text-ink">whsec_…</code> 是否已写入后端 <code class="font-mono text-xs">STRIPE_WEBHOOK_SECRET</code>（不要用 Dashboard 里网页端点的密钥代替 CLI 的 whsec）</li>
          <li>修改 <code class="font-mono text-xs">.env</code> 后是否已<strong>重启</strong> uvicorn</li>
        </ul>
      </div>
      <p v-if="errorText" class="mt-3 text-sm text-red-800">{{ errorText }}</p>
      <details v-if="sessionId" class="mt-6 text-left">
        <summary class="cursor-pointer text-xs font-semibold text-ink-mute">支付会话编号（客服排错用）</summary>
        <p class="mt-2 break-all font-mono text-xs text-ink-soft">{{ sessionId }}</p>
      </details>
      <div class="mt-8 flex flex-wrap justify-center gap-3">
        <RouterLink to="/" class="btn-primary !py-2 !px-5 !text-sm">回到首页</RouterLink>
        <RouterLink :to="{ path: '/', hash: '#pricing' }" class="btn-secondary !py-2 !px-5 !text-sm">
          查看定价
        </RouterLink>
      </div>
    </div>
  </div>
</template>
