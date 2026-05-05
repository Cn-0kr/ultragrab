<script setup lang="ts"></script>

<template>
  <footer class="mt-12 border-t-2 border-ink/10 bg-white/60">
    <div class="mx-auto max-w-6xl px-4 py-10 md:px-8">
      <div class="grid gap-6 md:grid-cols-[2fr_1fr_1fr]">
        <div>
          <div class="flex items-center gap-2">
            <span class="grid h-9 w-9 place-items-center rounded-full border-2 border-ink bg-brand text-white shadow-sticker-sm">▶</span>
            <span class="text-lg font-display">UltraGrab</span>
          </div>
          <p class="mt-3 max-w-sm text-sm text-ink-soft">
            基于 yt-dlp 的万能视频下载工具。MVP 阶段，开放预览。
          </p>
        </div>
        <div>
          <div class="text-xs font-bold uppercase tracking-wider text-ink-mute">产品</div>
          <ul class="mt-2 space-y-1 text-sm text-ink-soft">
            <li><a href="#workbench" class="hover:text-ink">开始下载</a></li>
            <li><a href="#pricing" class="hover:text-ink">Pro 会员</a></li>
            <li><a href="#faq" class="hover:text-ink">常见问题</a></li>
          </ul>
        </div>
        <div>
          <div class="text-xs font-bold uppercase tracking-wider text-ink-mute">合规</div>
          <ul class="mt-2 space-y-1 text-sm text-ink-soft">
            <li>仅用于授权内容</li>
            <li>不绕过 DRM / 付费墙</li>
            <li>用户自行确认版权</li>
          </ul>
        </div>
      </div>
      <div class="mt-8 flex flex-col items-start justify-between gap-2 border-t border-ink/10 pt-4 text-xs text-ink-mute md:flex-row">
        <span>© {{ new Date().getFullYear() }} UltraGrab. All rights reserved.</span>
        <span>Built with Vue 3 · FastAPI · yt-dlp</span>
      </div>
    </div>
  </footer>
</template>
