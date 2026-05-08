<script setup lang="ts">
import faqs from '@/content/faq.json'
</script>

<template>
  <section id="faq" class="mx-auto max-w-4xl scroll-mt-20 px-4 py-10 md:px-8 md:py-16">
    <h2 class="text-3xl md:text-4xl">常见问题</h2>
    <div class="mt-6 flex flex-col gap-3">
      <details
        v-for="(item, idx) in faqs"
        :key="idx"
        class="card group p-5 transition-colors open:bg-white"
      >
        <summary class="flex cursor-pointer list-none items-center justify-between gap-4 text-lg font-semibold">
          <span>{{ item.q }}</span>
          <span class="inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-ink bg-cream text-lg transition-transform group-open:rotate-45">+</span>
        </summary>
        <p class="mt-3 text-ink-soft">{{ item.a }}</p>
      </details>
    </div>
  </section>
</template>
