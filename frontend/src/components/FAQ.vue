<script setup lang="ts">
const faqs = [
  {
    q: '支持哪些视频平台？',
    a: '依赖开源项目 yt-dlp，覆盖 YouTube、Bilibili、TikTok、Instagram、X、Facebook、Vimeo、Twitch 等 1800+ 站点。部分平台需要账号登录才能访问的内容，MVP 版暂不支持。',
  },
  {
    q: '三种下载模式有什么区别？',
    a: '服务端模式会在后端合并最高画质的音视频并暂存在磁盘，带宽消耗最大但最稳定；直链代理通过后端转发，可保留 Referer/UA 等请求头，避免部分平台的 403；直链 302 最轻量，但部分平台做强 Referer 校验时会失败。',
  },
  {
    q: '为什么有些视频下载失败？',
    a: '常见原因包括：地域限制、需要登录、平台反爬、直链 5 分钟内过期、ffmpeg 未安装导致无法合并。错误提示会在任务卡片上明确显示，必要时切换到另一种模式再试。',
  },
  {
    q: '这个工具是否合法？',
    a: '本站是个人使用工具，类似浏览器右键另存。你必须保证只下载自己有权访问的公开或授权内容，不得用于绕过 DRM、付费墙或未授权的抓取。上传/二次分发责任由用户承担。',
  },
  {
    q: '字幕翻译什么时候上线？',
    a: '原字幕下载已在开发中。字幕翻译、AI 总结等高级能力将作为 Pro 专属特性，在付费通道开放后上线。',
  },
]
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
