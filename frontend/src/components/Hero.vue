<script setup lang="ts">
defineEmits<{ cta: [] }>()

const platforms = [
  'YouTube', 'TikTok', 'Bilibili', 'Instagram', 'X', 'Facebook', 'Vimeo', 'Twitch', 'SoundCloud',
]
</script>

<template>
  <section class="relative overflow-hidden">
    <div class="pointer-events-none absolute -top-10 right-0 hidden h-56 w-56 rotate-12 rounded-full bg-accent/40 blur-3xl md:block" />
    <div class="pointer-events-none absolute -bottom-16 left-10 hidden h-56 w-56 -rotate-12 rounded-full bg-brand/30 blur-3xl md:block" />

    <div class="mx-auto max-w-6xl px-4 py-14 md:px-8 md:py-20">
      <div class="flex flex-col items-start gap-6">
        <span class="tag">批量 · 高清 · 字幕 · 1800+ 平台</span>
        <h1 class="text-4xl leading-[1.05] md:text-6xl lg:text-7xl">
          像右键"另存为"一样<br />
          下载<span class="bg-accent px-3 py-1 inline-block -rotate-2 border-2 border-ink shadow-sticker-sm">任何视频</span>
        </h1>
        <p class="max-w-xl text-lg text-ink-soft md:text-xl">
          粘贴链接即刻解析。服务端合并最高画质、直链代理保留 Referer、字幕原汁保留。
          桌面和手机都顺手，不装软件、不跳广告。
        </p>
        <div class="flex flex-wrap gap-3">
          <button class="btn-primary" @click="$emit('cta')">
            立即粘贴链接
            <span aria-hidden class="-mr-1">→</span>
          </button>
          <a href="#pricing" class="btn-secondary">查看 Pro 权益</a>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-xs font-semibold text-ink-mute">
          <span class="uppercase tracking-wider">支持平台</span>
          <span
            v-for="p in platforms"
            :key="p"
            class="rounded-full border border-ink/20 bg-white/60 px-3 py-1"
          >
            {{ p }}
          </span>
          <span class="rounded-full border-2 border-ink bg-accent px-3 py-1 text-ink">+1800</span>
        </div>
      </div>
    </div>
  </section>
</template>
