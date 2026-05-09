<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '@/composables/useAuth'

defineEmits<{ cta: [] }>()

const route = useRoute()
const router = useRouter()
const { user, refresh, logout } = useAuth()

const displayName = computed(() => {
  const e = user.value?.email
  if (!e) return ''
  const [name] = e.split('@')
  return name.length > 12 ? `${name.slice(0, 12)}…` : name
})

const isPro = computed(() => Boolean(user.value?.has_active_subscription))

onMounted(() => void refresh())

watch(
  () => route.fullPath,
  () => void refresh(),
)

function onLogout() {
  logout()
  if (route.name === 'billing-success') void router.push('/')
}
</script>

<template>
  <header class="sticky top-0 z-30 border-b-2 border-ink/10 bg-cream/80 backdrop-blur">
    <div class="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 md:px-8">
      <RouterLink to="/" class="flex min-w-0 items-center gap-2">
        <span
          class="grid h-9 w-9 shrink-0 place-items-center rounded-full border-2 border-ink bg-brand text-base font-display text-white shadow-sticker-sm"
        >▶</span>
        <span class="truncate text-lg font-display tracking-tight">UltraGrab</span>
      </RouterLink>
      <nav class="hidden items-center gap-6 text-sm font-semibold text-ink-soft md:flex">
        <RouterLink :to="{ path: '/', hash: '#workbench' }" class="hover:text-ink">工作台</RouterLink>
        <RouterLink :to="{ path: '/', hash: '#pricing' }" class="hover:text-ink">Pro 会员</RouterLink>
        <RouterLink :to="{ path: '/', hash: '#faq' }" class="hover:text-ink">常见问题</RouterLink>
      </nav>
      <div class="flex shrink-0 items-center gap-2">
        <template v-if="user">
          <div
            class="flex min-w-0 max-w-[10.5rem] items-center gap-1.5 rounded-full border-2 px-2 py-1 sm:max-w-[13rem]"
            :class="
              isPro
                ? 'border-amber-500/70 bg-gradient-to-r from-amber-100/90 via-accent/40 to-brand/15 shadow-sticker-sm'
                : 'border-ink/10 bg-white/50'
            "
            :title="user.email"
          >
            <span
              v-if="isPro"
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-amber-600/40 bg-gradient-to-b from-amber-200 to-amber-400 text-amber-950 shadow-inner"
              aria-hidden="true"
              title="Pro 会员"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path
                  d="M5 16L3 8l5.5 3L12 4l3.5 7L21 8l-2 8H5zm1.5-2h11L17 10.5 12 13 7 10.5 6.5 14z"
                />
              </svg>
            </span>
            <span
              v-else
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-ink/15 bg-cream text-ink-soft"
              aria-hidden="true"
              title="免费用户"
            >
              <svg class="h-3.5 w-3.5 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" d="M12 12a3.5 3.5 0 100-7 3.5 3.5 0 000 7z" />
                <path stroke-linecap="round" d="M5 20a7 7 0 0114 0" />
              </svg>
            </span>
            <span
              class="min-w-0 truncate text-xs font-semibold"
              :class="isPro ? 'text-ink' : 'font-medium text-ink-soft'"
              >{{ displayName }}</span
            >
            <span
              v-if="isPro"
              class="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-amber-700/25 bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-950"
            >
              <span class="sr-only">您已是 Pro 会员</span>
              <span aria-hidden="true">★</span>
              <span aria-hidden="true">Pro</span>
            </span>
          </div>
          <button type="button" class="btn-ghost !px-3 !py-2 !text-xs" @click="onLogout">退出</button>
        </template>
        <template v-else>
          <RouterLink
            :to="{
              path: '/login',
              query: {
                next: route.name === 'login' || route.name === 'register' ? '/' : route.fullPath,
              },
            }"
            class="btn-ghost !px-3 !py-2 !text-xs"
          >
            登录
          </RouterLink>
        </template>
        <button class="btn-primary !py-2 !px-3 !text-sm md:!px-4" @click="$emit('cta')">开始下载</button>
      </div>
    </div>
  </header>
</template>
