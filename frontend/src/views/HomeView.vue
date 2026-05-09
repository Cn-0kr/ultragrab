<script setup lang="ts">
import Hero from '@/components/Hero.vue'
import DownloadWorkbench from '@/components/DownloadWorkbench.vue'
import PricingTeaser from '@/components/PricingTeaser.vue'
import FAQ from '@/components/FAQ.vue'
import { inject, onUnmounted, ref, watch, type Ref } from 'vue'

const workbenchRef = ref<InstanceType<typeof DownloadWorkbench> | null>(null)
const workbenchFocusRef = inject<Ref<(() => void) | null>>('workbenchFocusRef')

watch(
  workbenchRef,
  (v) => {
    if (!workbenchFocusRef) return
    workbenchFocusRef.value = v ? () => v.focusInput() : null
  },
  { immediate: true },
)

onUnmounted(() => {
  if (workbenchFocusRef) workbenchFocusRef.value = null
})

function focusInput() {
  workbenchRef.value?.focusInput()
}
</script>

<template>
  <div>
    <Hero @cta="focusInput" />
    <DownloadWorkbench ref="workbenchRef" />
    <PricingTeaser />
    <FAQ />
  </div>
</template>
