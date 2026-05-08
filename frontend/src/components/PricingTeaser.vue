<script setup lang="ts">
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
        <div class="absolute right-6 top-6 rotate-6">
          <span class="tag !bg-accent/90 !shadow-sticker-sm">限时 5 折</span>
        </div>
        <h2 class="text-3xl">Pro</h2>
        <p class="mt-1 text-ink-soft">批量、翻译、4K、一整天省下 2 小时。</p>
        <div class="mt-4 flex items-baseline gap-2">
          <span class="text-4xl font-display">¥39</span>
          <span class="text-sm text-ink-mute line-through">¥78</span>
          <span class="text-sm text-ink-mute">/month</span>
        </div>
        <ul class="mt-4 grid grid-cols-1 gap-2 text-ink-soft sm:grid-cols-2">
          <li v-for="f in proFeatures" :key="f" class="flex items-center gap-2">
            <span class="inline-flex h-5 w-5 items-center justify-center rounded-full border-2 border-ink bg-accent text-xs">★</span>
            {{ f }}
          </li>
        </ul>
        <button class="btn-primary mt-6" disabled>支付即将开放</button>
        <p class="mt-2 text-xs text-ink-mute">当前为 MVP，付费通道接入 Stripe / Creem 前显示为占位。</p>
      </article>
    </div>
  </section>
</template>
