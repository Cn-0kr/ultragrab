# SEO / GEO 相关对话沉淀

本文档汇总仓库中与 **SEO、GEO（AI 可发现性）** 相关的设计结论与对话记录，便于后续维护与排障。

## 1. 已落地的技术方案（UltraGrab 前端）

### 1.1 构建与环境变量

- 生产构建需设置 **`VITE_SITE_ORIGIN`**（无尾斜杠），用于生成 canonical、`og:url`、`twitter:url`、**`sitemap.xml`** 中的绝对地址以及 FAQ JSON-LD 的 `@id`。
- 可选 **`VITE_OG_IMAGE`**（完整 URL）；未设置时回退为 `{origin}/favicon.svg`。分享图建议后续使用约 **1200×630** 的专用资源。
- 说明见：[`frontend/.env.example`](frontend/.env.example)。

### 1.2 `index.html` 与鱼厂 TDK 对齐要点

参考仓库内 **[`docs/鱼厂SEO优化工作流.md`](鱼厂SEO优化工作流.md)**：

- **Title**：三段式（页面 - 产品 | 核心介绍），与 `vite.config.ts` 中 `DEFAULT_OG_TITLE` 保持一致。
- **Description**：核心能力 + 价值 + **CTA**；与 `DEFAULT_OG_DESCRIPTION`、OG/Twitter 描述一致。
- **Keywords**：保留 `meta keywords`（兼顾百度等习惯），与页面内容真实相关、忌堆砌。
- **robots**：`index, follow`。
- 其他：**`og:site_name`**、FAQ **JSON-LD（FAQPage）** 在存在 `VITE_SITE_ORIGIN` 的构建产物中注入；无 origin 时仍注入 FAQ 结构化数据，但不注入依赖绝对 URL 的社交 meta。

### 1.3 数据来源与 GEO 辅助

- FAQ 正文：**[`frontend/src/content/faq.json`](../frontend/src/content/faq.json)**，由 [`FAQ.vue`](../frontend/src/components/FAQ.vue) 引用，与 JSON-LD 同源，避免「页面与标记不一致」。
- **[`frontend/public/llms.txt`](../frontend/public/llms.txt)**：面向人与 AI 助理的站点说明，随静态资源部署到站点根路径。

### 1.4 `robots.txt`

- 由构建脚本写入 `dist/robots.txt`。
- 对 **GPTBot、ChatGPT-User、ClaudeBot、anthropic-ai、PerplexityBot、Google-Extended、Applebot-Extended、meta-externalagent** 等显式 **`Allow: /`**，再 **`User-agent: *`** + **`Allow: /`**；有 origin 时追加 **`Sitemap:`**。
- 意图：**政策表达**（欢迎常见 AI/研究爬虫），与通配允许一致，并非单独封锁其他爬虫。

### 1.5 单页应用（SPA）与收录

- 未引入 SSR；缓解手段：**首屏 HTML 富 TDK**、**FAQ JSON-LD**、**llms.txt**。若后续收录不足，可另立 **SSG/预渲染** 项。

---

## 2. 语义化标题：H1 / H2 / H3 的作用（简述）

| 标签 | 作用 |
|------|------|
| **H1** | 页面**主标题**，说明整页主题；每页通常 **1 个**，权重最高。 |
| **H2** | **大章节**标题，划分主要板块。 |
| **H3** | **小节**标题，隶属于某一 H2 下的细分。 |

要求层级连续（H1 → H2 → H3），勿跳级、勿多 H1；益处：**SEO 理解结构** + **读屏与无障碍导航**。视觉效果应用 CSS 控制，语义上仍应使用正确级别的标题标签。

---

## 3. 浏览器 SEO 插件提示：是否采纳修改（结论：不修改）

插件常见两条提示：

1. **缺少社交分享标签（OG / Twitter）**  
   - **判断**：方向正确，但需区分**检测环境**。本地 `dev` 或未配置 `VITE_SITE_ORIGIN` 的构建会**故意不注入**绝对 URL 的社交 meta，插件可能报「缺少」，属预期。生产环境应用带 **`VITE_SITE_ORIGIN` 的 build** 部署后，查看「页面源代码」应能看到完整 OG/Twitter。若仍缺失，再查 CDN/网关是否改写 `head`。

2. **Meta description 建议 140–160 字符**  
   - **判断**：可作参考；Google 多为约 **150–160 英文字符**量级，**中文按结果页像素截断**，不宜死卡数字。当前中文描述以**前部信息密度 + 通顺 + CTA** 为主即可；**本次对话决定：不为卡字数单独改版**。

---

## 4. 参考外链（编程导航课程章节）

以下链接曾作为「GEO/SEO 教程」参考；公开抓取曾难以获得正文，**执行上以仓库内《鱼厂 SEO 优化工作流》为准**：

- <https://www.codefather.cn/course/2027618983506640897/section/2036378576458121218>
- <https://www.codefather.cn/course/2027618983506640897/section/2036378652605710337>

---

## 5. 上线与校验清单（摘自实施笔记）

- 生产构建：`VITE_SITE_ORIGIN` 已设置；检查 `dist/index.html`（meta + JSON-LD）、`dist/robots.txt`、`dist/sitemap.xml`、`dist/llms.txt`。
- [Google Rich Results Test](https://search.google.com/test/rich-results) 校验 FAQ（需可公网访问的 URL 或粘贴 HTML）。
- Search Console / 百度站长：提交 sitemap（按实际使用的搜索引擎）。

---

*文档生成自项目内 SEO/GEO 实施与讨论整理，后续迭代请同步更新本节与 `frontend/.env.example`。*
