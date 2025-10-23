# Market Lens Realtime Console

Market Lens has now switched to **FastAPI + WebSocket + React** combination, providing a smoother real-time experience:

- ✅ FastAPI provides REST & WebSocket interfaces
- ✅ WebSocket real-time push of model tokens, tool status, and logs
- ✅ React frontend implements streaming chat, session management, and configuration switches

## Quick Start

> Two terminal windows need to be opened in the root directory.

### 1. Start FastAPI Backend

```bash
export GOOGLE_API_KEY=your_api_key
uvicorn manager.server.app:app --reload --port 8000
```

### 2. Start React Frontend

```bash
cd frontend
npm install
npm run dev
```

Will automatically proxy to `http://localhost:8000`, visit `http://localhost:5173` in your browser.

## Directory Structure Overview

```
manager/server/       # FastAPI application (REST + WebSocket)
frontend/             # React + Vite frontend
manager/memory_manager.py  # Session / memory management
manager/log_stream.py      # Log capture and queue
```

To customize API address or WebSocket address, set in `frontend/.env`:

```
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000
```

## Streaming Event Convention

WebSocket `/ws/chat/{session_id}` will push the following events:

| type    | Description                     |
|---------|--------------------------|
| token             | Model incremental tokens (for streaming replies)           |
| status            | Brief status text (e.g., "Generating…")              |
| progress          | Progress and log events (includes tool stages, logs, etc.)      |
| thinking_status   | Agent thinking status (start / stop / error)|
| thinking_content  | Thinking content fragments returned by Gemini                 |
| final             | Final answer and complete message list                    |
| error             | Error message                                   |

The frontend can display streaming replies and output real-time logs based on this, and reuse historical sessions.

---

If you need to continue using historical sessions, the backend will automatically supplement the owner field for old data on first access, no manual migration needed.
