<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, api, setToken } from '@/api/client'
import { useAuth } from '@/composables/useAuth'
import { navigateAfterAuth } from '@/utils/authRedirect'

const route = useRoute()
const router = useRouter()
const { refresh } = useAuth()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMsg = ref<string | null>(null)
const hintMsg = ref<string | null>(null)

const passwordHint = computed(() => {
  if (password.value.length > 0 && password.value.length < 8) {
    return '密码至少 8 位'
  }
  return null
})

onMounted(() => {
  document.title = '注册 - UltraGrab'
})

async function onSubmit() {
  errorMsg.value = null
  hintMsg.value = null
  if (password.value.length < 8) {
    errorMsg.value = '密码至少 8 位'
    return
  }
  submitting.value = true
  try {
    const res = await api.register({
      email: email.value.trim(),
      password: password.value,
    })
    setToken(res.access_token)
    await refresh()
    navigateAfterAuth(router, Array.isArray(route.query.next) ? route.query.next[0] : route.query.next)
  } catch (e) {
    if (e instanceof ApiError) {
      errorMsg.value = e.message
      hintMsg.value = e.hint ?? null
    } else {
      errorMsg.value = '网络异常，请稍后重试。'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-md px-4 py-16 md:py-24">
    <div class="card p-8">
      <h1 class="text-2xl font-display">注册账号</h1>
      <p class="mt-1 text-sm text-ink-soft">注册后即可开通 Pro（Stripe）。我们不会把密码用于其他用途。</p>

      <form class="mt-6 space-y-4" @submit.prevent="onSubmit">
        <div>
          <label for="reg-email" class="block text-sm font-semibold text-ink">邮箱</label>
          <input
            id="reg-email"
            v-model="email"
            type="email"
            autocomplete="email"
            required
            class="mt-1 w-full rounded-xl border-2 border-ink/15 bg-white px-4 py-2.5 text-ink shadow-inner focus:border-brand focus:outline-none"
            placeholder="you@example.com"
          />
        </div>
        <div>
          <label for="reg-password" class="block text-sm font-semibold text-ink">密码（≥8 位）</label>
          <input
            id="reg-password"
            v-model="password"
            type="password"
            autocomplete="new-password"
            required
            minlength="8"
            class="mt-1 w-full rounded-xl border-2 border-ink/15 bg-white px-4 py-2.5 text-ink shadow-inner focus:border-brand focus:outline-none"
          />
          <p v-if="passwordHint" class="mt-1 text-xs text-amber-800">{{ passwordHint }}</p>
        </div>

        <div
          v-if="errorMsg"
          class="rounded-xl border-2 border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          {{ errorMsg }}
          <p v-if="hintMsg" class="mt-1 text-xs text-red-800/90">{{ hintMsg }}</p>
        </div>

        <button type="submit" class="btn-primary w-full justify-center" :disabled="submitting">
          {{ submitting ? '注册中…' : '注册并登录' }}
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-ink-soft">
        已有账号？
        <RouterLink
          :to="{ path: '/login', query: route.query }"
          class="font-semibold text-brand underline-offset-2 hover:underline"
        >
          登录
        </RouterLink>
        <span class="mx-1">·</span>
        <RouterLink to="/" class="font-semibold text-ink underline-offset-2 hover:underline">回首页</RouterLink>
      </p>
    </div>
  </div>
</template>
