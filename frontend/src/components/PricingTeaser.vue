<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, api, getToken } from '@/api/client'
import { useAuth } from '@/composables/useAuth'

const freeFeatures = [
  '单条链接解析',
  '最高 1080p 服务端合并',
  '直链代理 / 302 重定向',
  '原字幕下载',
]

const proFeatures = [
  '批量 / 剪贴板识别',
  '4K / 60fps 无损合并',
  '字幕翻译（多语种）',
  '无限下载历史',
  '去水印 & 格式转换',
  '移动端吸底下载条',
  '优先客服 + 早鸟功能',
]

const router = useRouter()
const { user, refresh } = useAuth()
const checkoutLoading = ref(false)
const checkoutError = ref<string | null>(null)
const hintError = ref<string | null>(null)

onMounted(() => void refresh())

const isPro = computed(() => Boolean(user.value?.has_active_subscription))

async function onSubscribe() {
  checkoutError.value = null
  hintError.value = null
  if (!getToken()) {
    void router.push({ path: '/login', query: { next: '/#pricing' } })
    return
  }
  checkoutLoading.value = true
  try {
    await refresh()
    const { url } = await api.createCheckout()
    window.location.assign(url)
  } catch (e) {
    if (e instanceof ApiError) {
      checkoutError.value = e.message
      hintError.value = e.hint ?? null
      if (e.code === 'already_subscribed') await refresh()
      if (e.code === 'unauthorized') {
        void router.push({ path: '/login', query: { next: '/#pricing' } })
      }
    } else {
      checkoutError.value = '无法创建支付会话，请稍后重试。'
    }
  } finally {
    checkoutLoading.value = false
  }
}
</script>

<template>
  <section id="pricing" class="mx-auto max-w-6xl scroll-mt-20 px-4 py-10 md:px-8 md:py-16">
    <div class="grid gap-6 md:grid-cols-2">
      <article class="card p-8">
        <h2 class="text-3xl">Free</h2>
        <p class="mt-1 text-ink-soft">够用、够快，右键解决一切。</p>
        <div class="mt-4 text-4xl font-display">¥0<span class="text-base text-ink-mute">/forever</span></div>
        <ul class="mt-4 space-y-2 text-ink-soft">
          <li v-for="f in freeFeatures" :key="f" class="flex items-center gap-2">
            <span class="inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-ink bg-white text-xs">✓</span>
            {{ f }}
          </li>
        </ul>
        <a href="#workbench" class="btn-secondary mt-6">直接去下载</a>
      </article>

      <article class="relative card overflow-hidden p-8">
        <h2 class="text-3xl">Pro</h2>
        <p class="mt-1 text-ink-soft">批量、翻译、4K、一整天省下 2 小时。</p>
        <div class="mt-4 flex items-baseline gap-2">
          <span class="text-4xl font-display">¥12</span>
          <span class="text-sm text-ink-mute">/month</span>
        </div>
        <ul class="mt-4 grid grid-cols-1 gap-2 text-ink-soft sm:grid-cols-2">
          <li v-for="f in proFeatures" :key="f" class="flex items-center gap-2">
            <span class="inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-ink bg-accent text-xs">★</span>
            {{ f }}
          </li>
        </ul>

        <div
          v-if="checkoutError"
          class="mt-4 rounded-xl border-2 border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          {{ checkoutError }}
          <p v-if="hintError" class="mt-1 text-xs text-red-800/90">{{ hintError }}</p>
        </div>

        <button
          v-if="isPro"
          type="button"
          class="btn-secondary mt-6 w-full cursor-default opacity-90"
          disabled
        >
          您已是 Pro 会员
        </button>
        <button
          v-else
          type="button"
          class="btn-primary mt-6 w-full justify-center"
          :disabled="checkoutLoading"
          @click="onSubscribe"
        >
          {{ checkoutLoading ? '跳转 Stripe…' : '开通 Pro（Stripe）' }}
        </button>
        <p class="mt-2 text-xs text-ink-mute">安全由 Stripe 处理；本站不保存卡号。重复开通会被系统拒绝，请在邮箱查收订阅凭证。</p>
      </article>
    </div>
  </section>
</template>
