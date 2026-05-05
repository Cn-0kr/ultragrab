# 分阶段交付计划 - 万能视频下载站

> 本文件是项目计划的**权威版本**。`.cursor/plans/*.plan.md` 是草稿，最终以本文件为准。计划若有变动需改本文件。

## 阶段总览

| 阶段 | 主题 | 产出 | 验收方式 |
| --- | --- | --- | --- |
| 0 | 文档落地 | `docs/` 四份主文档 | 可读、引用清晰、与计划一致 |
| 1 | 后端核心 API | FastAPI + yt-dlp 封装 | `curl` / Swagger 跑通三种模式 |
| 2 | 前端骨架 | Vue 3 + Vite + Tailwind | 本地 dev 可独立启动，页面骨架齐 |
| 3 | 端到端 MVP ⭐ | 前后端联调 | 三个主流平台 × 三种模式各跑一次成功 |
| 4 | UI 精雕 + 付费引导 | Video School 风格 + 会员卡 | 1440 / 390 双断点形态稳定 |
| 5 | 扩展能力 | 字幕/进度/历史/移动端 | 分别完成演示 + 已知限制说明 |

## 阶段 0 — 文档落地（先于写代码）

**交付物**

- `docs/README.md`：导航。
- `docs/requirements.md`：需求分析。
- `docs/design.md`：方案设计。
- `docs/plan.md`：本文件。

**验收点**：四份文档齐备、可读、引用关系清晰。

## 阶段 1 — 后端核心 API（FastAPI + yt-dlp 封装）

**范围**

- 初始化 `backend/`：目录结构、`requirements.txt`、`uvicorn` 启动脚本、`.env.example`。
- 实现 `backend/app/ytdlp_service.py`：解析、格式整理、服务端下载、直链解析、字幕支持。
- 接口：
  - `GET /api/health`
  - `POST /api/parse`：返回标题、封面、时长、格式列表（清晰度/大小/音视频标志）、字幕语言、`task_id`。
  - `POST /api/parse/batch`
  - `POST /api/download`：`mode` = `server | proxy | redirect`
  - `GET /api/tasks/{id}`
  - `GET /api/files/{id}`
  - `GET /api/proxy`
  - `GET /api/redirect`
- 基础防护：URL 协议/内网过滤、单批 URL 上限、并发限制、任务超时、临时文件清理。

**验收点（阶段内自测，不依赖前端）**

- `uvicorn` 启动成功，`/docs` 可打开。
- `curl` 对 YouTube 或 Bilibili 公开视频完成：
  - 解析（`POST /api/parse`）得到格式列表。
  - 服务端下载（`mode=server`）：轮询 `/api/tasks/{id}` 到 `done`，`GET /api/files/{id}` 能拿到文件。
  - 直链代理（`mode=proxy`）：`GET /api/proxy?task=...` 能流式返回数据。
  - 直链重定向（`mode=redirect`）：`GET /api/redirect?task=...` 返回 302。

## 阶段 2 — 前端骨架（Vue 3 + Vite + Tailwind）

**范围**

- 初始化 `frontend/`：Vite + Vue 3 + TS + Tailwind，配置开发代理到 FastAPI。
- 组件：`Hero.vue`、`DownloadWorkbench.vue`（输入 + 格式选择 + 模式切换 + 任务卡）、`PricingTeaser.vue`、`FAQ.vue`、`Footer.vue`。
- 状态管理：composable 优先，不引入 pinia。
- `api/client.ts`：API 封装，MVP 阶段即对真实后端，不做额外 mock。
- 响应式 grid、品牌 token（颜色、字体、手绘贴纸位）先落到 `tailwind.config.js`。UI 精雕留阶段 4。

**验收点**

- `npm run dev` 启动成功，默认页面骨架齐备。
- 组件目录结构与 `design.md` 一致。
- 开发代理生效，可从前端调到 `/api/health`。

## 阶段 3 — 端到端 MVP ⭐（前后端联调，必须可跑通）

**范围**

- 前端调用真实后端：`/api/parse` → 展示视频信息与格式列表 → 选择清晰度 + 下载模式 → 触发下载。
- 服务端模式：前端轮询 `/api/tasks/{id}`，完成后点击下载按钮拿文件。
- 直链模式：前端直接跳转到 `/api/proxy` 或 `/api/redirect`，浏览器原生下载。
- 简单错误提示：非法 URL / 解析失败 / 平台不支持 / 直链过期建议切换模式。
- 合规声明在首页可见。

**验收清单**

- YouTube、Bilibili、X/Twitter 任选 2 个公开链接，三种模式各跑一次成功。
- 桌面 1440px + 移动 390px 双断点下首页可用。
- 非法 URL、不可下载链接、直链过期都有明确提示，不卡住界面。
- **这是第一次批量验收节点**。

## 阶段 4 — UI 精雕 + 付费引导

- 按 Video School 精修：白底、青绿色主色、亮黄强调、粗黑标题、手绘贴纸、圆角大卡。
- 付费引导：Free vs Pro 对比卡、会员价值点（批量、4K、去水印、字幕翻译、无限历史、手机端优先）、限时 `GET 50% OFF` 横幅、FAQ。
- 支持平台 logo 墙：YouTube / TikTok / Bilibili / Instagram / X / Facebook / Vimeo 等，强调 1800+ 网站。
- 首屏交错出场动画、hover 微交互。
- 验收点：1440 桌面 + 390 移动两个断点下形态正确、视觉稳定。

## 阶段 5 — 扩展能力

- 字幕下载：前端解析后显示字幕语言列表，下载时可勾选；翻译/AI 总结做 `Pro 专属` 占位入口。
- 下载进度：服务端模式接 `progress_hooks`，通过 `/api/tasks/{id}` 或 SSE 推前端，显示百分比 + 速度 + ETA。
- 历史记录：`localStorage` 存最近任务，支持重试、清空。
- 移动端优化：大按钮、吸底下载条、粘贴剪贴板识别、批量粘贴体验调优。
- 验收点：字幕、进度、历史、移动端分别完成演示 + 已知限制说明。

## 文档维护节奏（全局）

- 每完成一个阶段：必须回写 `docs/changelog.md`（简述做了什么、验证了什么、已知限制）。
- 涉及架构/接口变更：同步更新 `docs/design.md` 相关小节；如果决策有权衡，新增 `docs/decisions/NNN-*.md`。
- 接口改动：同步更新 `docs/api.md`。
- 需求范围调整：同步更新 `docs/requirements.md`。
