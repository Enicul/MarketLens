# Market Lens Realtime Console

Market Lens 现已切换为 **FastAPI + WebSocket + React** 组合，提供更顺畅的实时体验：

- ✅ FastAPI 提供 REST & WebSocket 接口
- ✅ WebSocket 实时推送模型 Token、工具状态、日志
- ✅ React 前端实现流式聊天、会话管理、配置开关

## 快速启动

> 需要在根目录打开两个终端窗口。

### 1. 启动 FastAPI 后端

```bash
export GOOGLE_API_KEY=你的密钥
uvicorn manager.server.app:app --reload --port 8000
```

### 2. 启动 React 前端

```bash
cd frontend
npm install
npm run dev
```

默认会自动代理到 `http://localhost:8000`，浏览器访问 `http://localhost:5173` 即可。

## 目录结构速览

```
manager/server/       # FastAPI 应用（REST + WebSocket）
frontend/             # React + Vite 前端
manager/memory_manager.py  # 会话 / 记忆管理
manager/log_stream.py      # 日志捕获与队列
```

如需自定义 API 地址或 WebSocket 地址，可在 `frontend/.env` 中设置：

```
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000
```

## 流式事件约定

WebSocket `/ws/chat/{session_id}` 将推送以下事件：

| type    | 描述                     |
|---------|--------------------------|
| token             | 模型增量 Token（用于流式回复）           |
| status            | 简短状态文本（如“生成中…”）              |
| progress          | 进度及日志事件（含工具阶段、日志等）      |
| thinking_status   | 正在思考的 Agent 状态（开始 / 停止 / 错误）|
| thinking_content  | Gemini 返回的思考内容片段                 |
| final             | 最终回答及完整消息列表                    |
| error             | 错误提示                                   |

前端可据此显示流式回复、输出实时日志，并复用历史会话。

---

如需继续沿用历史会话，首次访问时后台会自动为旧数据补齐 owner 字段，无需手动迁移。
