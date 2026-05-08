# Ultragrab（万能视频下载站）

基于 [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) 的在线视频/音频/字幕下载工具，覆盖 1800+ 视频平台。

**前后端分离架构：**

- 前端：Vue 3 + Vite + TypeScript + Tailwind CSS
- 后端：FastAPI + yt-dlp（Python）+ ffmpeg（可选）
- 无数据库，任务状态放内存，下载文件放本地临时目录，定时清理。

## 目录结构

```
ultragrab/
├─ docs/        # 项目文档（需求 / 方案 / 计划 / API / 决策）
├─ backend/     # FastAPI + yt-dlp 后端
└─ frontend/    # Vue 3 + Vite 前端
```

## 文档

所有项目文档集中在 [docs/](./docs/)：

- [docs/README.md](./docs/README.md) — 文档导航
- [docs/requirements.md](./docs/requirements.md) — 需求分析
- [docs/design.md](./docs/design.md) — 方案设计
- [docs/plan.md](./docs/plan.md) — 分阶段交付计划

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:        source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 可选：按需修改
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/docs` 看 Swagger。

> **可选依赖：** 安装 [ffmpeg](https://ffmpeg.org/download.html) 并加入 PATH，以获得"合并最佳音视频 + 嵌字幕"能力。未安装时会自动降级为单文件最佳质量。

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认 `http://localhost:5173`，Vite 会把 `/api/*` 代理到 `http://127.0.0.1:8000`。

### AI 学习助手（可选）

依赖 **DeepSeek API**。在 `backend/.env` 中配置 `DEEPSEEK_API_KEY`（可参考 `backend/.env.example`）。前端解析任务成功后，工作台展开「AI 学习助手」可使用字幕列表、摘要（SSE）、思维导图（Mermaid，支持全屏与 **PNG/SVG** 导出）、字幕 **SRT/TXT** 导出、基于字幕的问答。无平台字幕且已配置 `SILICONFLOW_API_KEY` 时会走 ASR 转写后再生成摘要/导图/问答。详见 [docs/design.md](./docs/design.md) 八点五与 0.5.0+ 前端说明、`docs/changelog.md`。

**字幕获取策略：**

1. **平台字幕（优先）：** 通过 yt-dlp 或 B 站专用 API（WBI 签名 + 多源 Fallback）获取字幕。
2. **ASR 语音转写（自动降级，0.4.0+）：** 当平台字幕不可用时，自动提取音频并调用 SiliconFlow ASR 生成文字稿。需在 `backend/.env` 中配置 `SILICONFLOW_API_KEY`。

```env
# ASR 语音转写（可选，推荐配置）
SILICONFLOW_API_KEY=sk-xxxxxxx          # SiliconFlow API 密钥（需完成实名认证）
SILICONFLOW_API_BASE=https://api.siliconflow.cn  # 默认值，国内用 .cn
SILICONFLOW_ASR_MODEL=FunAudioLLM/SenseVoiceSmall  # 免费模型
```

**B 站字幕策略（0.3.0+）：** 解析 Bilibili 链接时，后端通过 **WBI 签名 + 多源 Fallback**（View API → Player WBI API → AI 摘要 API）尝试获取字幕，多数公开稿件匿名即可命中。`need_login_subtitle=True` 的稿件需配置 `YTDLP_COOKIE_FILE`（Netscape cookies.txt）或依赖 ASR 转写降级。

## 合规声明

本工具仅用于下载用户**有权访问**的公开或已授权内容（类似浏览器右键保存）。不得用于绕过 DRM、付费墙、会员限制或任何未授权内容的抓取。用户对下载内容的合法性负责。
