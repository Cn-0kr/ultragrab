<script setup lang="ts">
import Hero from './components/Hero.vue'
import DownloadWorkbench from './components/DownloadWorkbench.vue'
import PricingTeaser from './components/PricingTeaser.vue'
import FAQ from './components/FAQ.vue'
import Footer from './components/Footer.vue'
import TopNav from './components/TopNav.vue'
import { ref } from 'vue'

const workbenchRef = ref<InstanceType<typeof DownloadWorkbench> | null>(null)

function focusInput() {
  workbenchRef.value?.focusInput()
}
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <TopNav @cta="focusInput" />
    <main class="flex-1">
      <Hero @cta="focusInput" />
      <DownloadWorkbench ref="workbenchRef" />
      <PricingTeaser />
      <FAQ />
    </main>
    <Footer />
  </div>
</template>
