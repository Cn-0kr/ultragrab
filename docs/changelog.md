# 交付变更记录 (Changelog)

> 每完成一个阶段必须回写本文件：做了什么、验证了什么、已知限制。

## 0.6.0 — 2026-05-08（工作台同屏：Flex 分栏 + 解析后自动摘要）

### 新增 / 改进

- **任务卡布局**：`DownloadWorkbench.vue` 在 `lg` 断点使用 **Flex 横向分栏**（左侧约 `basis 42%`：封面 + 格式/下载；右侧 `flex-1 min-w-0`：**AI 学习助手**，`sticky` + 限高滚动），小屏仍为纵向堆叠，便于一屏对照「下载信息」与「总结」。
- **自动摘要**：解析成功、`VideoSummary` 挂载后 **`autoSummarize` 为真** 时自动调用 `runSummary()`，无需再点「生成摘要」；`task_id` 维度去重，避免对同一任务重复触发。
- **Props 显式化**：工作台传入 `:default-open="true"`、`:auto-summarize="true"`、`embedded`（右侧嵌入式：边框/背景略收紧）。
- **展开与长耗时提示**：自动总结开始时 **`panelOpen = true`**；总结 Tab 在 **`transcriptLoading`** 与流式摘要阶段分别展示「拉取字幕/转写」与「流式生成摘要」说明，避免长视频（先 `/api/transcript` 再等 `/api/summarize`）被误认为无响应。
- **设计文档**：`docs/design.md` 增加「工作台同屏 + VideoSummary 集成（0.6.0+）」；目录结构索引补充 `VideoSummary.vue`。

### 验证（2026-05-08）

- `frontend`：`vue-tsc --noEmit`、`vite build` 通过。
- 后端：`POST /api/parse` + `POST /api/transcript` 实测长视频（如 YouTube `g_cU-DrUPGI`）转写阶段可达数十秒，前端进度文案与按钮「生成中…」状态一致。

### 已知限制

- **批量任务**：每条解析成功的任务各触发一次自动摘要，并发与 API 用量随任务数增加；若需「仅首条自动」或全局开关，可后续再加。
- 长视频无平台字幕时依赖 ASR，首包慢属预期，依赖文案与加载态降低误解。

---

## 0.5.0 — 2026-05-08（AI 面板：导图修复、导出、字幕语言 UX）

### 新增 / 改进

- **错误隔离**：`VideoSummary.vue` 中总结 / 字幕 / 导图 / 问答各用独立 `ref` 错误状态，错误仅出现在对应 Tab。
- **思维导图**：全屏预览（`Teleport` + 关闭按钮 + ESC）；区分 LLM 返回 **mindmap** 与 **flowchart**，避免误删 `-->` 导致只显示 `flowchart TD` 单框；mindmap 失败时降级为流程图树；去重渲染降低 Mermaid 报错。
- **导出**：导图支持 **PNG**（处理 `foreignObject` + base64 SVG 入 Canvas，避免污损画布）与 **SVG**；字幕支持 **SRT** 与 **TXT**；文件名优先使用 `videoTitle`（`DownloadWorkbench.vue` 传入 `metadata.title`）。
- **字幕语言 UX**：主行展示常用语言 + 钉选简体/繁体中文（`zh-Hans` 等）；大量自动翻译语言收入可搜索的折叠区。
- **后端**：`_MINDMAP_SYSTEM` 收紧节点文案规则，减少 Mermaid 语法错误。

### 文档

- `docs/design.md`：新增「前端 AI 面板：导图、导出与错误隔离（0.5.0+）」。

### 验证（2026-05-08）

- 本地启动 `uvicorn` + `vite`，浏览器：YouTube 解析 → 展开 AI 助手 → 导图生成、多节点展示、全屏与导出按钮可用；控制台无 `Tainted canvases` 报错。

### 已知限制

- 导图仍依赖模型输出合法 Mermaid；极端乱码时需用户「重新生成」。
- PNG 导出将 `foreignObject` 转为简单 `<text>`，复杂样式可能与屏显略有差异。

---

## 0.1.0 — 2026-05-04 (阶段 0–3 一次性交付，MVP 上线)

### 阶段 0 · 文档落地

- 新建 `docs/` 目录（README + requirements + design + plan + changelog）。
- 项目根新增 `README.md` 作为入口导航。
- `.cursor/plans/*.plan.md` 不再作为权威源，所有正式文档以 `docs/` 为准。

### 阶段 1 · 后端核心 API（FastAPI + yt-dlp）

- 新增 `backend/` 目录：`requirements.txt`、`.env.example`、`app/` 模块化骨架。
- `app/ytdlp_service.py` 封装 yt-dlp（解析、格式整理、服务端下载、直链解析、字幕）。
- `app/routes.py` 落地接口：
  - `GET /api/health`（含 ffmpeg 探测）
  - `POST /api/parse` / `POST /api/parse/batch`
  - `POST /api/download`（`mode = server | proxy | redirect`）
  - `GET /api/tasks/{id}` / `GET /api/files/{id}`
  - `GET /api/proxy`（透传 Range + http_headers）
  - `GET /api/redirect`（302）
- `app/task_store.py` 内存任务库 + 周期清理；`app/main.py` 装载 CORS、统一错误模型、文件清理后台任务。
- 安全约束：URL 协议白名单、`localhost` / 私有 IP 字面量拒绝、`format_id` 受控枚举、proxy 仅查表不接受外部 URL。
- 本地验证（curl / Invoke-RestMethod）：YouTube 公开视频 `Me at the zoo`，三种模式（server / proxy / redirect）全部通过。

### 阶段 2 · 前端骨架（Vue 3 + Vite + Tailwind）

- 新增 `frontend/`：Vite + Vue 3 + TS + Tailwind + 自定义 Video-School 风 token（青绿主色 / 亮黄强调 / 粗黑标题 / 圆角大卡 / sticker 阴影）。
- 组件：`TopNav`、`Hero`、`DownloadWorkbench`、`PricingTeaser`、`FAQ`、`Footer`、`Spinner`。
- `api/client.ts` 封装 fetch + ApiError + 文件 URL 构造；`utils/format.ts` 处理时长/字节/百分比/ETA。
- 开发代理：`/api` → `http://127.0.0.1:8000`。

### 阶段 3 · 端到端 MVP（前后端联调）

- 工作台支持单条 / 批量输入、格式下拉、模式切换（server / proxy / redirect）、任务卡进度条 + 速度 + ETA。
- 服务端模式：前端轮询 `/api/tasks/{id}`，到 `done` 后展示"保存到本地"按钮。
- 直链模式：调用 `/api/download` 拿到 proxy/redirect URL，自动新窗口触发浏览器下载。
- 通过浏览器实测：YouTube 公开链接 → 解析成功 → 服务端模式合并下载完成 → 切换 proxy 模式同链接再次成功（浏览器 200 流式返回）。
- 修复一处 Vue 3 反应性陷阱：原始对象推入 `ref` 数组后直接修改属性不触发更新，已改为 `reactive(...)` 包装。

### 已知限制

- 任务状态在内存中，进程重启即丢失；保留 1 小时后自动清理临时文件。
- 不支持需要登录态的内容（YouTube 会员视频、B 站大会员独享、Twitter 私密帖等）。
- 直链 302 模式对强 Referer 平台（B 站等）可能失败，前端不会自动回退，由用户切换到 proxy。
- ffmpeg 缺失会自动降级为 `best` 单文件模式，最高画质合并不可用。
- 工作台已支持字幕语言选择（含 AI 面板）；服务端下载仍可传 `subtitle_langs`。
- 付费通道（Pro 卡）仅占位，实际支付能力待接入。
- 移动端粘贴剪贴板识别、吸底下载条等优化排在阶段 5。

### 下一步（阶段 4 / 5）

- 阶段 4：Video School 视觉精修 + 平台 logo 墙 + 限时促销横幅 + 入场动画。
- 阶段 5：字幕勾选 UI、`localStorage` 历史、SSE 进度推送、移动端粘贴优化、Pro 占位入口。

---

## 0.4.0 — 2026-05-07（ASR 语音转写 Fallback + 前端适配）

### 新增

- `backend/app/asr_service.py`：完整 ASR 管线——yt-dlp 提取音频（bestaudio → mp3 64kbps）→ SiliconFlow `/v1/audio/transcriptions` 转写 → 按句切分 + 按字符比例分配时间戳 → 生成 `TranscriptCue` 列表。
- `backend/app/ai_config.py`：新增 `siliconflow_api_key()`、`siliconflow_api_base()`、`siliconflow_asr_model()` 配置读取函数；`load_dotenv` 改用 `override=True` 确保 `.env` 变更即时生效。
- `backend/app/ai_routes.py`：`_ensure_transcript()` 新增 Phase 2（ASR Fallback）——当 Phase 1（平台字幕）全部失败且 `SILICONFLOW_API_KEY` 已配置时，自动调用 `asr_for_task()` 转写音频生成字幕。ASR 结果以 `_asr` 语言 key 写入 `transcript_cache`，后续 summarize / mindmap / chat 可复用。
- `backend/.env`：新增 `SILICONFLOW_API_KEY`、`SILICONFLOW_API_BASE`、`SILICONFLOW_ASR_MODEL` 环境变量。

### 前端

- `VideoSummary.vue`：移除"生成摘要/导图/问答"按钮的 `!subtitleOptions.length` 禁用条件，无平台字幕时仍可点击（后端自动 ASR）。
- AI 面板说明文案从"基于平台字幕"更新为"基于字幕/语音转写"；无字幕提示从警告色改为中性提示"将自动使用 ASR 语音转写"。

### 文档

- `docs/design.md`：新增"ASR 语音转写 Fallback（SiliconFlow，0.4.0+）"章节，含触发条件、流程、环境变量、限制说明；更新目录结构索引补充新增文件。
- `README.md`：补充 ASR Fallback 配置说明。

### 验证（2026-05-07）

- **BV1g8d8B6ENk**（无平台字幕，`need_login_subtitle=True`）：
  - Phase 1 平台字幕：View API / Player WBI API / AI 摘要 API 三源均返回空 → 确认无平台字幕。
  - Phase 2 ASR Fallback：yt-dlp 下载音频 → SiliconFlow 转写 → 成功获得 35 cues / 1258 字符。
  - AI 摘要：基于 ASR 文本调用 DeepSeek 生成结构化摘要（主题概括 / 核心观点 / 关键步骤 / 术语定义 / 行动建议），内容准确。
  - 前端完整 UI 测试通过：解析 → 展开 AI 助手 → 点击"生成摘要" → 流式渲染摘要。

### 已知限制

- SiliconFlow 免费模型 `SenseVoiceSmall` 限制：音频 ≤ 1 小时、文件 ≤ 50 MB；超长视频自动跳过 ASR。
- ASR 返回纯文本无时间戳，字幕视图中的时间为按字符比例估算值。
- SiliconFlow 账号需完成实名认证后 API Key 才可用。
- ASR 需下载音频流，首次调用较慢（约 15–25 秒，视网络和视频时长而定）。

---

## 0.3.0 — 2026-05-07（B 站 WBI 签名 + 多源字幕 Fallback）

### 新增

- `backend/app/bilibili_subs.py` 全面重写：
  - 实现 WBI 签名算法（`img_key` + `sub_key` → 置换表 → `mixin_key` → MD5 → `w_rid`），密钥缓存 1 小时自动刷新。
  - 多源瀑布 Fallback：View API → Player WBI API → AI 摘要 API，三源按优先级尝试、合并去重。
- `backend/app/ytdlp_service.py`：解析 B 站链接时调用 `bilibili_subs.probe()` 合并字幕列表。
- `backend/app/subtitle_extractor.py`：字幕拉取支持 B 站多源路径。

### 文档

- `docs/design.md`：新增"B 站字幕：WBI 签名 + 多源 Fallback（0.3.0+）"章节。

### 已知限制

- 匿名 + WBI 签名可获取多数公开稿件的 AI 字幕，但 `need_login_subtitle=True` 时仍需 Cookie。
- AI 摘要端点部分稿件无数据（极短视频、纯音乐类）。
- WBI 密钥每日更替，代码已做自动刷新；若 B 站变更置换表需手动更新 `_MIXIN_KEY_ENC_TAB`。

---

## 0.2.1 — 2026-05-07（B 站 AI 字幕无 Cookie 接入）

### 新增

- `backend/app/bilibili_subs.py`：直接调用 B 站 Player API（`/x/player/v2`）获取 AI 自动字幕轨道（ai-zh / ai-en / ai-ja …），无需 Cookie，多数公开稿件匿名可用。
- 解析阶段（`ytdlp_service.parse_url`）：当 extractor 为 BiliBili 时，额外 probe Player API 并将 AI 轨道合并去重到字幕列表。
- 字幕拉取（`subtitle_extractor.fetch_subtitles_to_cues`）：若请求语言为 ai-*，走 Bilibili JSON → SRT 本地转换路径，不经过 yt-dlp；失败时自动回退原逻辑。

### 文档

- `README.md`：更新 B 站字幕说明为「优先尝试 AI 字幕端点，无需 Cookie」。
- `docs/design.md` 八点五：增补 AI 字幕端点策略、代码索引、去重规则及限制。

### 验证（2026-05-07）

- **BV1g8d8B6ENk**：`/x/player/v2` 匿名返回 `need_login_subtitle=True`，`subtitles=[]`。**未命中**——该稿件需登录态才返回字幕。
- **BV1vZ4y1M7mQ**：`need_login_subtitle=False`，但 `subtitles=[]`。**未命中**——当前 API 匿名不返回 AI 字幕。
- 额外测试 B 站热门榜 15 条视频，全部匿名返回 0 条字幕，无论 `need_login_subtitle` 值如何。
- **结论**：B 站 `/x/player/v2` 当前在完全匿名（无 SESSDATA）下不返回 AI 字幕。代码路径正确（BV 提取、View/Player API 调用、JSON→SRT 转换、`parse_srt` roundtrip 均通过），当配置 Cookie 或 B 站放开匿名限制时即可生效。目前 `probe()` 返回空列表，`fetch_subtitles_to_cues` 正确回退到 yt-dlp 路径。

### 已知限制

- **当前状态**：B 站 Player API 在无 Cookie 状态下不返回 AI 字幕列表（含 `ai-zh`）；需配置 `YTDLP_COOKIE_FILE` 以传入 `SESSDATA` 等鉴权信息。
- `/x/player/v2` 匿名请求长期有效（返回 200），但 `subtitles` 字段为空；若 B 站全面切换到 WBI 签名校验，需后续补实现。
- 极少数稿件（超短/纯音乐）B 站不生成 AI 字幕，此时列表仍为空。
- 本次不实现 WBI 签名算法，不做本地 Whisper ASR 兜底。

---

## 0.2.0 — 2026-05-06（AI 学习助手 + B 站字幕说明）

### 新增

- 后端：`/api/transcript`、`/api/summarize`（SSE）、`/api/mindmap`、`/api/chat`（SSE）；DeepSeek 客户端与字幕缓存；`subtitle_extractor` 仅拉字幕不写视频。
- 解析阶段 `listsubtitles`，修正 yt-dlp 默认不填充 `info["subtitles"]` 导致前端看不到字幕语言的问题。
- 可选环境变量 `YTDLP_COOKIE_FILE`，解析/服务端下载/ AI 拉字幕共用，用于 B 站等「接口要求登录才返回字幕列表」的稿件。
- 前端：`VideoSummary.vue`（摘要 / 字幕 / 导图 / 问答）、`videoAi.ts`；工作台挂载 AI 面板；依赖 `marked`、`mermaid`。

### 文档

- `README.md`、`docs/design.md` 增补 AI 配置与 **B 站 `need_login_subtitle` / Cookie** 说明；恢复并扩展 `backend/.env.example`。

### 已知问题（持续跟踪）

- **B 站部分视频**：网页登录可见字幕，但匿名 Player API 字幕列表为空；必须配置 `YTDLP_COOKIE_FILE`（已登录账号导出）后重新解析，详见设计文档「八点五」。
- **抖音等**：若无 yt-dlp 可识别的字幕轨道，AI 功能不可用（首期不接 ASR）。
- 个别 BV 在不同出口 IP/风控下行为可能不一致；以 `yt-dlp --list-subs` 实测为准。
