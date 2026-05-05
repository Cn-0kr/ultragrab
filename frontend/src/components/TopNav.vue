<script setup lang="ts">
defineEmits<{ cta: [] }>()
</script>

<template>
  <header class="sticky top-0 z-30 border-b-2 border-ink/10 bg-cream/80 backdrop-blur">
    <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 md:px-8">
      <a href="#" class="flex items-center gap-2">
        <span
          class="grid h-9 w-9 place-items-center rounded-full border-2 border-ink bg-brand text-base font-display text-white shadow-sticker-sm"
        >▶</span>
        <span class="text-lg font-display tracking-tight">UltraGrab</span>
      </a>
      <nav class="hidden items-center gap-6 text-sm font-semibold text-ink-soft md:flex">
        <a href="#workbench" class="hover:text-ink">工作台</a>
        <a href="#pricing" class="hover:text-ink">Pro 会员</a>
        <a href="#faq" class="hover:text-ink">常见问题</a>
      </nav>
      <button class="btn-primary !py-2 !px-4 !text-sm" @click="$emit('cta')">开始下载</button>
    </div>
  </header>
</template>
