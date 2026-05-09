<script setup lang="ts">
import { provide, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import TopNav from './components/TopNav.vue'
import Footer from './components/Footer.vue'

const router = useRouter()
const workbenchFocusRef = ref<(() => void) | null>(null)
provide('workbenchFocusRef', workbenchFocusRef)

async function onCta() {
  const fn = workbenchFocusRef.value
  if (fn) fn()
  else {
    await router.push({ name: 'home' })
    await nextTick()
    workbenchFocusRef.value?.()
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <TopNav @cta="onCta" />
    <main class="flex-1">
      <RouterView />
    </main>
    <Footer />
  </div>
</template>
