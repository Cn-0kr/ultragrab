import { defineConfig, loadEnv, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'

const SEO_PLACEHOLDER = '<!-- __SEO_EXTRA_HEAD__ -->'

/** 与 index.html 中 title / og:title / twitter:title 保持一致（鱼厂 TDK 三段式） */
const DEFAULT_OG_TITLE = '在线视频下载与AI摘要 - UltraGrab | 1800+平台高清解析'

/** 与 index.html 中 description / og:description 保持一致；前段核心信息 + CTA */
const DEFAULT_OG_DESCRIPTION =
  'UltraGrab 一站式在线视频工具：支持 YouTube、Bilibili、TikTok 等 1800+ 站点解析，服务端高清合并、直链代理与 302 下载，原字幕及同页 AI 摘要、思维导图与视频问答。免安装浏览器即用，适合学习与素材归档。立即粘贴链接免费体验。'

const OG_SITE_NAME = 'UltraGrab'

const FAQ_JSON_PATH = path.join(__dirname, 'src/content/faq.json')

/** 显式 Allow：与通配规则一致，便于声明欢迎常见 AI / 研究爬虫（UA 以各厂商文档为准）。 */
const ROBOTS_AI_USER_AGENTS = [
  'GPTBot',
  'ChatGPT-User',
  'ClaudeBot',
  'anthropic-ai',
  'PerplexityBot',
  'Google-Extended',
  'Applebot-Extended',
  'meta-externalagent',
] as const

type FaqItem = { q: string; a: string }

function escapeHtmlAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
}

function readFaqItems(): FaqItem[] {
  const raw = fs.readFileSync(FAQ_JSON_PATH, 'utf8')
  return JSON.parse(raw) as FaqItem[]
}

function buildFaqJsonLd(origin: string): string {
  const items = readFaqItems()
  const doc: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map((item) => ({
      '@type': 'Question',
      name: item.q,
      acceptedAnswer: {
        '@type': 'Answer',
        text: item.a,
      },
    })),
  }
  if (origin) {
    doc['@id'] = `${origin}/#faq`
  }
  const json = JSON.stringify(doc, null, 0)
  return `\n    <script type="application/ld+json">${json}</script>`
}

function buildRobotsTxt(origin: string): string {
  const lines: string[] = [
    '# UltraGrab — 下方为常见 AI/研究类爬虫的显式 Allow，与 User-agent: * 的开放策略一致；非单独封锁其他 Bot。',
  ]
  for (const ua of ROBOTS_AI_USER_AGENTS) {
    lines.push('', `User-agent: ${ua}`, 'Allow: /')
  }
  lines.push('', 'User-agent: *', 'Allow: /')
  if (origin) {
    lines.push('', `Sitemap: ${origin}/sitemap.xml`)
  }
  return `${lines.join('\n')}\n`
}

function seoInjectPlugin(mode: string): Plugin {
  const env = loadEnv(mode, process.cwd(), '')
  const originRaw = env.VITE_SITE_ORIGIN?.trim() ?? ''
  const origin = originRaw.replace(/\/+$/, '')
  const ogImageOverride = env.VITE_OG_IMAGE?.trim() ?? ''

  let outDir = path.resolve(process.cwd(), 'dist')

  return {
    name: 'seo-inject',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir)
    },
    transformIndexHtml(html) {
      const faqLd = buildFaqJsonLd(origin)

      if (!origin) {
        return html.replace(SEO_PLACEHOLDER, faqLd)
      }

      const imageUrl = ogImageOverride || `${origin}/favicon.svg`
      const block = `
    <link rel="canonical" href="${origin}/" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="${escapeHtmlAttr(OG_SITE_NAME)}" />
    <meta property="og:title" content="${escapeHtmlAttr(DEFAULT_OG_TITLE)}" />
    <meta property="og:description" content="${escapeHtmlAttr(DEFAULT_OG_DESCRIPTION)}" />
    <meta property="og:locale" content="zh_CN" />
    <meta property="og:url" content="${origin}/" />
    <meta property="og:image" content="${escapeHtmlAttr(imageUrl)}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeHtmlAttr(DEFAULT_OG_TITLE)}" />
    <meta name="twitter:description" content="${escapeHtmlAttr(DEFAULT_OG_DESCRIPTION)}" />
    <meta name="twitter:url" content="${origin}/" />
    <meta name="twitter:image" content="${escapeHtmlAttr(imageUrl)}" />${faqLd}`

      return html.replace(SEO_PLACEHOLDER, block)
    },
    writeBundle() {
      fs.mkdirSync(outDir, { recursive: true })
      fs.writeFileSync(path.join(outDir, 'robots.txt'), buildRobotsTxt(origin), 'utf8')

      if (origin) {
        const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${origin}/</loc>
  </url>
</urlset>
`
        fs.writeFileSync(path.join(outDir, 'sitemap.xml'), sitemap, 'utf8')
      } else if (fs.existsSync(path.join(outDir, 'sitemap.xml'))) {
        fs.unlinkSync(path.join(outDir, 'sitemap.xml'))
      }
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [vue(), seoInjectPlugin(mode)],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
