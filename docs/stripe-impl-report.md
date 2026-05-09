# Stripe 会员落地报告（v0.7.0 + v0.7.1）

> 对应方案：[`plan-stripe-membership-jwt-sqlite.md`](./plan-stripe-membership-jwt-sqlite.md)  
> **v0.7.0**：后端（SQLite、JWT、Checkout、Webhook）+ CORS/配置  
> **v0.7.1**：前端登录/注册/结账/成功页、Webhook 与幂等修复、StripeObject 序列化、本地 pytest — 详见 [`changelog.md`](./changelog.md) 节「0.7.1」

> ~~前端尚未实施~~ **已完成**（Vue Router、`PricingTeaser` 实接 checkout、`/billing/success` 轮询 `me`、TopNav Pro 标识）。

---

## 一、本次工作交付清单

### 1. 配置与依赖

- **`backend/requirements.txt`** 新增：
  - `stripe>=11.0.0` — Stripe 官方 Python SDK
  - `PyJWT>=2.9.0` — JWT 编解码
  - `passlib[bcrypt]>=1.7.4` — 密码哈希
  - `email-validator>=2.2.0` — Pydantic `EmailStr` 校验依赖
- **`backend/app/settings.py`** 扩展字段（`Settings` dataclass）：
  - `jwt_secret`、`jwt_expires_seconds`（默认 7 天）
  - `stripe_secret_key`、`stripe_webhook_secret`、`stripe_price_pro_monthly`
  - `public_frontend_origin`（默认 `http://127.0.0.1:5173`，生产应改为 `https://ultragrab.0kr.xin`）
  - `billing_db_path`（默认 `backend/billing.db`）
  - `ensure_dirs()` 同步创建 DB 父目录
- **`backend/.env.example`** 增补 Auth/Stripe/PUBLIC_FRONTEND_ORIGIN 注释模板（不含真实密钥）。
- **`backend/app/main.py`** 修复 CORS bug：
  - 旧：`allow_origins=settings.cors_origins or ["*"]` + `allow_credentials=True` 在空列表时退化为「通配符 + credentials」，浏览器会拒绝。
  - 新：分支处理——空列表 → `["*"]` + `credentials=False`；非空列表 → 显式列表 + `credentials=True`。
- **价格对齐**：`frontend/src/components/PricingTeaser.vue` 由 `¥39/月（划线 ¥78）` 改为 **`¥12/月`**，与 Stripe 计划与 Dashboard 保持一致。

### 2. 数据层（SQLite）

新增 [`backend/app/db.py`](../backend/app/db.py)：

- 表结构与索引：
  - `users(id PK UUID, email UNIQUE, password_hash, stripe_customer_id, created_at)`
  - `subscriptions(stripe_subscription_id PK, user_id FK→users, stripe_price_id, status, current_period_end, cancel_at_period_end, updated_at)` + `idx_user_id`、`idx_status`
  - `stripe_events(event_id PK, type, received_at)` 用于 Webhook 幂等
- 连接管理：`@contextmanager connect()` 自动 commit/rollback/close；首次访问时按需 `executescript(_SCHEMA)`，幂等。
- Repository API：`create_user / get_user_by_email / get_user_by_id / set_stripe_customer_id / get_user_by_customer_id / upsert_subscription / update_subscription_by_stripe_id / get_active_subscription / get_latest_subscription / has_stripe_event / remember_event`（`remember_event` 仅在 Webhook **成功**处理业务后调用；入队前用 `has_stripe_event` 对已成功事件返回 dedupe；`INSERT OR IGNORE` 防止并发双写）。
- **v0.7.1 修正**：此前若先 `remember` 再处理且处理抛 500，会导致 Stripe 重试时被误判为已处理；现已改为「先处理、成功后再 remember」。

### 3. 认证

新增 [`backend/app/security.py`](../backend/app/security.py)：

- `passlib.CryptContext(schemes=["bcrypt"])` 提供 `hash_password / verify_password`。
- `issue_token(user_id, email)`：HS256 + `sub/email/iat/exp` claims。
- `decode_token(token)`：失败返回 `None`；任何异常都不会泄漏内部错误。

新增 [`backend/app/auth_routes.py`](../backend/app/auth_routes.py)（前缀 `/api/auth`）：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 邮箱+密码（≥8 位）注册，并发场景靠 `IntegrityError` 收敛为 409 |
| POST | `/api/auth/login` | 校验密码并签发 JWT |
| GET | `/api/auth/me` | Bearer 鉴权，返回用户基本信息 + 当前订阅快照 |

- `get_current_user`：FastAPI 依赖项，统一从 `Authorization: Bearer ...` 提取并解码 token，失败返回 401（错误体沿用 `ErrorPayload` 模型）。
- `_require_jwt_configured()`：未设置 `JWT_SECRET` 时返回 503（明示需要服务端配置），避免静默通过。

新增 [`backend/app/billing_schemas.py`](../backend/app/billing_schemas.py)：`RegisterRequest / LoginRequest / TokenResponse / SubscriptionView / MeResponse / CheckoutResponse`，与现有 `schemas.py` 解耦（计费系统单列，避免污染下载相关模型）。

### 4. 计费

新增 [`backend/app/billing_routes.py`](../backend/app/billing_routes.py)（前缀 `/api/billing`）：

- `POST /api/billing/checkout`（**必须 Bearer 鉴权**）：
  1. 校验 `STRIPE_SECRET_KEY` + `STRIPE_PRICE_PRO_MONTHLY`，缺失返回 503。
  2. 若用户已有 active/trialing 订阅 → 409 `already_subscribed`，避免重复扣费。
  3. 若 `users.stripe_customer_id` 为空 → `stripe.Customer.create(email, metadata.app_user_id)` 并写回 DB。
  4. `stripe.checkout.Session.create(mode="subscription", line_items=[{price, qty}], customer, client_reference_id=user.id, metadata.user_id=..., success_url, cancel_url, allow_promotion_codes=True)`。
  5. 返回 `{ "url": session.url }`。
- `success_url` 拼接 `{public_frontend_origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`；`cancel_url` 回到 `/#pricing`。

### 5. Webhook

新增 [`backend/app/webhook_routes.py`](../backend/app/webhook_routes.py)：

- `POST /api/stripe/webhook`：
  - 用 `await request.body()` 读 **raw bytes**（不消费 JSON 中间件）。
  - `stripe.Webhook.construct_event(...)` 校验 `Stripe-Signature`，签名失败一律 400。
  - **幂等（v0.7.1）**：若 `has_stripe_event` 已存在则直接 `200` + `deduplicated`；否则先执行业务，**成功后再** `remember_event`；StripeObject 用 `to_dict()` 归一化，展开字段用 `_stripe_id` 等解析。
  - 处理失败抛 500，让 Stripe 触发自动重试。
- 当前已处理事件：
  - `checkout.session.completed`：从 `client_reference_id`/`metadata.user_id` 解析 user_id → 写回 `customer_id`（如果首次）→ `Subscription.retrieve` 拉取最终状态 → `upsert_subscription`（payload 经 `_as_dict`，兼容 API `2026-xx` 展开字段）。
  - `customer.subscription.created/updated/deleted`：`_extract_subscription_fields` 后 upsert 或按 `subscription_id` 更新。
  - `invoice.paid` / `invoice.payment_failed` / `invoice.payment_succeeded`：retrieve 订阅状态后做派生更新（`past_due` 等中间态可立即出现在 `/api/auth/me`）。
  - 其他事件类型：仅记日志。

### 6. 路由注册

`backend/app/main.py`：

```python
app.include_router(api_router)        # 既有 /api/parse / download 等
app.include_router(ai_router)         # 既有 /api/transcript / summarize 等
app.include_router(auth_router)       # ✅ 新增
app.include_router(billing_router)    # ✅ 新增
app.include_router(webhook_router)    # ✅ 新增
```

错误体走原有 `StarletteHTTPException` handler，统一为 `{"error": {"code","message","hint"}}` 格式。

---

## 二、Stripe Dashboard 配置步骤

> **重要**：先用「测试模式 (Test Mode)」跑通端到端，再切到 Live Mode。两套模式的密钥、Price、Webhook 密钥**互不通用**。

### 1. 创建产品与定价（Test Mode）

1. 登录 [https://dashboard.stripe.com](https://dashboard.stripe.com)，确认右上角处于「**Test Mode**」（小开关）。
2. 左侧导航 → `Product catalog` → `Add product`：
   - **Name**：`UltraGrab Pro`（任意，仅展示用）
   - **Pricing model**：`Recurring`（订阅）
   - **Price**：`12.00 CNY`
   - **Billing period**：`Monthly`
3. 创建完成后进入产品详情，复制底部 **Price ID**，形如 `price_1AbCdEfGh...`。
4. 写入服务端环境变量：
   ```
   STRIPE_PRICE_PRO_MONTHLY=price_1AbCdEfGh...
   ```

### 2. 取得 API 密钥

1. 左侧导航 → `Developers` → `API keys`。
2. 复制 `Secret key`（`sk_test_...`），写入：
   ```
   STRIPE_SECRET_KEY=sk_test_xxx...
   ```
   **此密钥仅服务端使用**，不要进 Git，不要进前端构建产物。

### 3. 配置 Webhook（本地开发）

本地用 Stripe CLI 转发到 FastAPI：

```bash
# 安装 Stripe CLI: https://stripe.com/docs/stripe-cli
stripe login
stripe listen --forward-to http://127.0.0.1:8000/api/stripe/webhook
```

CLI 启动后会输出一行：

```
> Ready! Your webhook signing secret is whsec_xxxxxxxxxxxxxxxx (^C to quit)
```

把这个 `whsec_...` 写入：
```
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxx
```

> 该值只在 CLI 运行期间有效；每次 `stripe listen` 会重新签发，需要更新 `.env` 后重启 FastAPI。

### 4. 配置 Webhook（生产）

1. 左侧导航 → `Developers` → `Webhooks` → `Add endpoint`。
2. **Endpoint URL**：`https://ultragrab.0kr.xin/api/stripe/webhook`
3. **Events to send**（最少集，与代码处理对齐）：
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
4. 创建后进入端点详情，**Reveal Signing Secret** 复制 `whsec_...`，写入生产环境的 `STRIPE_WEBHOOK_SECRET`。

### 5. Customer Portal（取消/管理订阅，可选第二期）

1. 左侧 → `Settings` → `Billing` → `Customer portal`。
2. 启用 `Allow customers to cancel subscriptions`、`Update payment method` 等开关。
3. 设置 **Default redirect link**：`https://ultragrab.0kr.xin/account`（前端账户页地址）。
4. 第二期再后端加 `POST /api/billing/portal` 调用 `stripe.billing_portal.Session.create(customer=..., return_url=...)` 即可。

### 6. 生产前自检清单

- [ ] 切换至 **Live Mode**，重新创建生产 `price_...` 并替换 `STRIPE_PRICE_PRO_MONTHLY`。
- [ ] 用生产密钥 `sk_live_...` 替换 `STRIPE_SECRET_KEY`。
- [ ] 重新创建生产 Webhook 端点，更新 `STRIPE_WEBHOOK_SECRET`。
- [ ] `PUBLIC_FRONTEND_ORIGIN=https://ultragrab.0kr.xin`，并确认 `CORS_ORIGINS` 包含同一域名。
- [ ] `JWT_SECRET` 使用强随机串：`python -c "import secrets;print(secrets.token_urlsafe(48))"`，且与本地不同。
- [ ] 回归一次完整流程：注册 → 登录 → checkout → 测试卡 `4242 4242 4242 4242`（Test Mode）/ 真实卡（Live）→ Webhook 命中 → `/api/auth/me` 返回 `has_active_subscription: true`。
- [ ] 反向验证：取消订阅（在 Stripe Dashboard 点 Cancel 或走 Portal）→ Webhook 触发 `customer.subscription.deleted` → `/api/auth/me` 显示 status 变更。

---

## 三、本地端到端联调脚本

```bash
# 1. 安装新依赖
cd backend && pip install -r requirements.txt

# 2. 配置 backend/.env
#    - JWT_SECRET=<token_urlsafe(48)>
#    - STRIPE_SECRET_KEY=sk_test_...
#    - STRIPE_PRICE_PRO_MONTHLY=price_...
#    - PUBLIC_FRONTEND_ORIGIN=http://127.0.0.1:5173

# 3. 终端 A：启动 FastAPI
uvicorn app.main:app --reload --port 8000

# 4. 终端 B：启动 Stripe CLI 转发
stripe listen --forward-to http://127.0.0.1:8000/api/stripe/webhook
#    将 whsec_... 写入 .env，再重启 FastAPI

# 5. 测试（curl 示例）
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"u1@example.com","password":"hunter2hunter2"}'
# → {"access_token": "...", "expires_in": 604800}

TOKEN=<access_token>

curl -X POST http://127.0.0.1:8000/api/billing/checkout \
  -H "Authorization: Bearer $TOKEN"
# → {"url": "https://checkout.stripe.com/c/pay/cs_test_..."}
# 用浏览器打开该 URL，输入测试卡 4242 4242 4242 4242 / 任意未来日期 / 任意 CVC

curl http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN"
# → {"has_active_subscription": true, "subscription": {"status": "active", ...}}
```

Webhook 重发幂等可在另一终端验证：

```bash
stripe trigger checkout.session.completed
# 第一次：业务成功后在 stripe_events 落库；重复同 event.id：has_stripe_event → 200 deduplicated
```

---

## 四、剩余工作（下一迭代）

| 类别 | 待办 | 文件 |
|---|---|---|
| Customer Portal | 后端 `POST /api/billing/portal`；前端已订阅用户「管理订阅」入口 | `billing_routes.py`、`PricingTeaser.vue` |
| 限流 | 注册/登录每 IP 限流 | `auth_routes.py` |
| 产品门禁 | 按需将 Pro 能力与下载/AI 路由绑定 JWT 或订阅状态 | `routes.py`、`ai_routes.py` 等 |

前端结账闭环、本地 pytest 已实现，见 **v0.7.1** / `changelog.md`。

---

## 五、关键文件速览（截至 v0.7.1）

```
backend/
├─ requirements.txt
├─ .env.example
├─ tests/test_stripe_webhook.py   ← v0.7.1：签名校验、Subscription to_dict 回归
└─ app/
   ├─ settings.py                  ← JWT、Stripe、load_dotenv(override=True)、_env_stripe_value
   ├─ main.py
   ├─ db.py                        ← has_stripe_event；成功后 remember_event
   ├─ security.py
   ├─ billing_schemas.py
   ├─ auth_routes.py
   ├─ billing_routes.py
   └─ webhook_routes.py            ← _as_dict / _event_data_object / _stripe_id / 幂等顺序

frontend/src/
├─ api/config.ts
├─ api/client.ts
├─ router/index.ts
├─ composables/useAuth.ts
├─ utils/authRedirect.ts
├─ views/HomeView.vue, LoginView.vue, RegisterView.vue, BillingSuccessView.vue
├─ components/PricingTeaser.vue, TopNav.vue
├─ App.vue, main.ts
└─ .env.example                   ← VITE_API_BASE
```
