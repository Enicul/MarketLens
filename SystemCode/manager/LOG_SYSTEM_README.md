# Real-Time Logging System Guide

## 🎯 Purpose

Continuously capture and stream execution logs from the Manager agent and all sub-agents so users no longer wait without feedback.

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│  Agent execution                        │
│    ↓                                    │
│  logging.info("[ANALYST] Collecting…")  │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  LogStreamHandler (custom handler)      │
│    ↓ pushes into queue                  │
│  Queue (thread-safe, 1000-item buffer)  │
└─────────────┬──────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  React frontend (WebSocket)             │
│    - Streams logs, status, tool events  │
│    - Supports streaming replies, level  │
│      highlighting                       │
└─────────────────────────────────────────┘
```

## 📝 Code Touchpoints

### 1. `log_stream.py`
- `LogStreamHandler`: custom logging handler.
- `LogStreamManager`: session-aware singleton manager.

### 2. `agent_stream_gradio.py`
```python
# Replace print statements with logging
print(f"[ANALYST] Collecting data…")
↓
logging.info(f"[ANALYST] Collecting data…")
```

### 3. FastAPI WebSocket Push
- `manager/server/app.py` `chat_websocket` creates sessions via `LogStreamManager`.
- `_forward_logs` drains the queue and pushes events to the frontend.
- React consumes `type: "log"` events through the `useChatWebSocket` hook.

## 🎨 Frontend Snapshot

```
📊 Market Lens AI
━━━━━━━━━━━━━━━━━━━━━━

🔍 Live Execution Logs [toggle]
    ✅ 10:15:30 [ANALYST] 📊 Collecting data: AAPL - news, fundamentals
    ✅ 10:15:45 [ANALYST] ✅ Finished collecting news
    ✅ 10:16:02 [RESEARCHER] 🔬 Launching research: AAPL
    ✅ 10:16:05 [Debate] Round 1/3 - Bullish stance…
    ✅ 10:16:12 [Debate] Round 1/3 - Bearish response…
    ✅ 10:16:35 [TRADER] 💹 Generating trading decision

💬 Conversation
━━━━━━━━━━━━━━━━━━━━━━
User: Analyze AAPL
...
```

## ⚙️ Configuration

### Log Level
```python
# Inside log_stream.py
handler.setLevel(logging.INFO)  # INFO, DEBUG, WARNING, ERROR
```

### Queue Size
```python
# Prevent unbounded growth
log_queue = queue.Queue(maxsize=1000)
```

### Display Count
```python
# app_streamlit.py
log_placeholder.markdown('\n\n'.join(log_lines[-50:]))  # Last 50 entries
```

## 🐛 Known Constraints

1. **Not truly real-time in Streamlit** – updates land after execution finishes.  
   Workaround: the current React + WebSocket stack removes this limitation.
2. **Per-session isolation** – logs are separated by `session_id`.  
   For global logs, adjust `LogStreamManager.create_session()`.
3. **Log format discipline** – agents must emit via `logging`, not `print`.  
   Core agents follow this; review sub-agents for stragglers.

## 🔥 Performance Optimizations

1. Drop entries when the queue is full to avoid blocking agent execution.
2. Limit frontend rendering to the most recent 50 entries.
3. Clean up sessions once work completes to prevent memory leaks.

## 🚀 Extensions

### Log Search
```python
search_term = st.text_input("Search logs")
filtered_logs = [log for log in all_logs if search_term in log['message']]
```

### Export Logs
```python
st.download_button("Download logs", '\n'.join(all_logs), "logs.txt")
```

### Level Filtering
```python
levels = st.multiselect("Log level", ["INFO", "WARNING", "ERROR"])
filtered = [log for log in all_logs if log['level'] in levels]
```

## 📌 Maintenance Notes

1. When adding new agents, always use `logging.info()` instead of `print()`.
2. Keep the `[MODULE] emoji message` format for consistency.
3. Ensure `cleanup_session()` is called to release queue resources.

## 🎓 Takeaway

Simple, efficient, thread-safe. Avoid unnecessary complexity—keep it reliable and maintainable.
