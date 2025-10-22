# 实时日志系统使用说明

## 🎯 功能

实时捕获并显示 Manager Agent 和所有 Sub-Agents 的执行日志，让用户不再傻等。

## 🏗️ 架构

```
┌─────────────────────────────────────────┐
│  Agent 执行                              │
│    ↓                                     │
│  logging.info("[ANALYST] 收集数据...")    │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  LogStreamHandler (捕获日志)             │
│    ↓ 推送到队列                          │
│  Queue (线程安全，1000条缓冲)             │
└─────────────┬───────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  React 前端 (WebSocket)                 │
│    - 页面实时显示日志、状态、工具事件     │
│    - 支持流式消息、高亮日志等级           │
└─────────────────────────────────────────┘
```

## 📝 代码修改点

### 1. 新增 `log_stream.py`
- `LogStreamHandler`: 自定义日志处理器
- `LogStreamManager`: 单例管理器，支持多会话

### 2. 修改 `agent_stream_gradio.py`
```python
# 替换所有 print 为 logging
print(f"[ANALYST] 收集数据...")
↓
logging.info(f"[ANALYST] 收集数据...")
```

### 3. FastAPI WebSocket 推送
- `manager/server/app.py` 中 `chat_websocket` 会调用 `LogStreamManager.create_session`
- `_forward_logs` 持续从队列读取日志并推送给前端
- React 端经由 `useChatWebSocket` 钩子接收 `type: "log"` 事件并增量渲染

## 🎨 前端效果

```
📊 Market Lens AI
━━━━━━━━━━━━━━━━━━━━━━

🔍 实时执行日志 [展开/折叠]
    ✅ 10:15:30 [ANALYST] 📊 收集数据: AAPL - news, fundamentals
    ✅ 10:15:45 [ANALYST] ✅ 成功收集: news
    ✅ 10:16:02 [RESEARCHER] 🔬 深度研究: AAPL
    ✅ 10:16:05 [Debate] Round 1/3 - Bullish speaking...
    ✅ 10:16:12 [Debate] Round 1/3 - Bearish responding...
    ✅ 10:16:35 [TRADER] 💹 生成交易决策

💬 对话界面
━━━━━━━━━━━━━━━━━━━━━━
用户: 分析 AAPL
...
```

## ⚙️ 配置项

### 日志级别
```python
# 在 log_stream.py 中修改
handler.setLevel(logging.INFO)  # INFO, DEBUG, WARNING, ERROR
```

### 队列大小
```python
# 防止内存溢出
log_queue = queue.Queue(maxsize=1000)
```

### 显示数量
```python
# app_streamlit.py
log_placeholder.markdown('\n\n'.join(log_lines[-50:]))  # 最多50条
```

## 🐛 已知限制

1. **非真正实时**: Streamlit 限制，只能在执行完成后显示
   - 解决方案：使用 WebSocket + 自定义前端（太复杂，不值得）
   
2. **跨会话日志**: 目前按 session_id 隔离
   - 如需全局日志，修改 `LogStreamManager.create_session()`

3. **日志格式**: 需要在各 Agent 中统一使用 `logging` 而非 `print`
   - 已修改主要位置，Sub-Agent 内部可能还有残留

## 🔥 性能优化

1. **队列满时丢弃**: 避免阻塞 Agent 执行
2. **限制显示数量**: 前端只显示最近 50 条
3. **会话清理**: 执行完成后自动清理队列

## 🚀 扩展建议

### 添加日志搜索
```python
# 在前端添加搜索框
search_term = st.text_input("搜索日志")
filtered_logs = [log for log in all_logs if search_term in log['message']]
```

### 导出日志
```python
# 添加下载按钮
st.download_button("下载日志", '\n'.join(all_logs), "logs.txt")
```

### 日志级别筛选
```python
# 添加级别选择器
levels = st.multiselect("日志级别", ["INFO", "WARNING", "ERROR"])
filtered = [log for log in all_logs if log['level'] in levels]
```

## 📌 维护要点

1. **新增 Agent 时**: 使用 `logging.info()` 而非 `print()`
2. **日志格式**: 统一 `[MODULE] emoji message` 格式
3. **清理机制**: 确保 `cleanup_session()` 被调用，防止内存泄漏

## 🎓 总结

简洁、高效、线程安全。别整那些花里胡哨的，够用就行。
