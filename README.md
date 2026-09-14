# Zhihu Knowledge Agent（知乎知识导航 Agent）

把一篇知乎内容转换成渐进式学习路线。

当前仓库支持提交知乎问题或回答链接，通过 AI 分析知识结构，再从知乎开放平台检索、筛选真实资料并生成学习路线。暂未使用数据库。

## 环境要求

- Python 3.11
- Node.js 20 或更高版本
- pnpm（也可以使用 npm）

## 启动后端

在项目根目录执行：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

后端默认运行在 `http://localhost:8000`。健康检查地址为 `http://localhost:8000/health`，交互式 API 文档地址为 `http://localhost:8000/docs`。

## 启动前端

另开一个终端，在项目根目录执行：

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

如果使用 npm，可将最后两条命令替换为：

```powershell
npm install
npm run dev
```

前端默认运行在 `http://localhost:3000`，并通过 `NEXT_PUBLIC_API_BASE_URL` 访问后端。

## 测试

后端测试：

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

前端检查：

```powershell
cd frontend
pnpm lint
pnpm build
```

## 当前接口

- `GET /health`：返回后端服务状态。
- `POST /api/routes/generate`：读取知乎问题或回答信息，搜索真实知乎内容并返回三段路线。
- `POST /api/routes/generate/stream`：按前置、当前、进阶三个阶段逐步返回路线。
- `POST /api/zhihu/search`：使用服务端密钥实验调用知乎开放平台搜索。
- `GET /api/auth/zhihu/login`：开始知乎 OAuth 授权。
- `GET /api/auth/zhihu/callback`：接收授权码并由后端换取 Token。
- `GET /api/auth/session`：返回公开的登录状态，不返回 Token。
- `POST /api/auth/logout`：清除登录会话。

## 知乎 OAuth 骨架

取得知乎审核发放的 `app_id` 和 `app_key` 后，在后端环境中配置：

```text
ZHIHU_OAUTH_APP_ID=你的_app_id
ZHIHU_OAUTH_APP_KEY=你的_app_key
ZHIHU_OAUTH_REDIRECT_URI=https://kanshan-knowledge-agent-api.onrender.com/api/auth/zhihu/callback
FRONTEND_URL=https://kanshan-knowledge-agent-web.onrender.com
SESSION_SECRET=一段足够长的随机字符串
```

申请材料中的回调地址必须与 `ZHIHU_OAUTH_REDIRECT_URI` 完全一致。`app_key`、`SESSION_SECRET` 和用户 Token 只能保存在后端，不能写进前端或提交到 GitHub。当前骨架仅实现已提供文档中的授权及 Token 交换；在获得官方用户信息接口文档前，页面只显示“知乎已授权”，不会虚构昵称或头像。

## 阶段 2 使用方式

前后端启动后，在首页输入一个知乎问题或回答链接并点击“生成学习路线”。当前官方能力尚不能可靠获取专栏文章详情，因此文章链接会返回明确提示。

生成路线前还需要在 `backend/.env` 中填写 OpenAI-compatible 服务商提供的 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `MODEL_NAME`。AI 只负责分析和筛选，最终资料链接必须来自知乎 API 返回的候选集合。

## 实验调用知乎搜索

复制 `backend/.env.example` 为 `backend/.env`，并在本地填写自己的 `ZHIHU_ACCESS_SECRET`。不要提交或分享这个文件。后端启动后可在 `http://127.0.0.1:8000/docs` 中测试 `POST /api/zhihu/search`，请求示例：

```json
{
  "query": "AI Agent",
  "count": 5,
  "sort_by": "VoteUpCount:desc"
}
```

## 部署到公网

当前 `render.yaml` 支持将前端和后端一同部署到 Render。

1. 将仓库推送到 GitHub，确认 `.env`、`.env.local` 没有被提交。
2. 在 Render 使用仓库根目录的 `render.yaml` 创建后端服务，并在控制台填写其中标记为 `sync: false` 的敏感环境变量。
3. 在 Vercel 导入同一仓库，将 Root Directory 设置为 `frontend`，并设置：

   ```text
   NEXT_PUBLIC_API_BASE_URL=https://你的后端地址.onrender.com
   ```

4. 将 Render 的 `FRONTEND_ORIGINS` 设置为最终 Vercel 地址，例如：

   ```text
   https://你的前端地址.vercel.app
   ```

5. 分别访问后端 `/health` 和前端首页完成移动网络测试。
