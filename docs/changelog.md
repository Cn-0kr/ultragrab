# 交付变更记录 (Changelog)

> 每完成一个阶段必须回写本文件：做了什么、验证了什么、已知限制。

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
