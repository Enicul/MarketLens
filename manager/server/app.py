from __future__ import annotations

import asyncio
import queue
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from langchain.callbacks.base import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from manager.agent_stream_gradio import build_main_agent
from manager.log_stream import get_log_manager
from manager.memory_manager import (
    MemorySessionManager,
    SessionMeta,
    get_memory_session_manager,
)
from manager.server.auth import AUTH_MANAGER, AuthSession, validate_credentials
from manager.server.messages import TOOL_DISPLAY_NAMES, format_chat_history
from manager.server.state import USER_STATE

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class LoginRequest(BaseModel):
    email: Optional[str] = Field(None, description="Account email")
    password: Optional[str] = Field(None, description="Account password")
    guest: bool = Field(False, description="Login as guest without password")


class LoginResponse(BaseModel):
    token: str
    email: str
    role: str
    display_name: str
    active_session_id: Optional[str]


class SessionResponse(BaseModel):
    id: str
    name: str
    created_at: str
    owner: Optional[str]
    is_active: bool = False


class SessionCreateRequest(BaseModel):
    name: Optional[str] = None


class SessionRenameRequest(BaseModel):
    name: str


class AnalysisConfigUpdate(BaseModel):
    news: Optional[bool] = None
    fundamentals: Optional[bool] = None
    market: Optional[bool] = None
    sentiment: Optional[bool] = None


class AnalysisConfigResponse(BaseModel):
    config: Dict[str, bool]


PROGRESS_TEMPLATES: Dict[str, Dict[str, str]] = {
    "call_analyst": {
        "start": "[ANALYST] 正在收集多维市场数据（新闻 / 基本面 / 市场 / 情绪）…",
        "end": "[ANALYST] 数据收集完成 ✅",
    },
    "call_researcher": {
        "start": "[RESEARCHER] 正在整合分析结果并撰写研报…",
        "end": "[RESEARCHER] 研究结论准备就绪 ✅",
    },
    "call_trader": {
        "start": "[TRADER] 正在生成交易计划与风险控制策略…",
        "end": "[TRADER] 交易建议已生成 ✅",
    },
    "call_risk_manager": {
        "start": "[RISK MANAGER] 正在复核风控参数与情景压力测试…",
        "end": "[RISK MANAGER] 风控复核完成 ✅",
    },
}

ANALYSIS_LABELS = {
    "news": "新闻",
    "fundamentals": "基本面",
    "market": "市场",
    "sentiment": "情绪",
}


def _progress_payload(
    *,
    message: str,
    tool: Optional[str] = None,
    stage: Optional[str] = None,
    level: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "type": "progress",
        "message": message,
        "tool": tool,
        "stage": stage,
        "timestamp": timestamp or datetime.utcnow().isoformat() + "Z",
    }
    if level:
        entry["level"] = level
    return entry


async def _push_progress(
    websocket: WebSocket,
    session_id: str,
    *,
    message: str,
    tool: Optional[str] = None,
    stage: Optional[str] = None,
    level: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> None:
    entry = _progress_payload(
        message=message,
        tool=tool,
        stage=stage,
        level=level,
        timestamp=timestamp,
    )
    await websocket.send_json(entry)
    try:
        MEMORY_MANAGER.append_progress(session_id, entry)
    except Exception:
        pass


def _extract_thinking_text(result: LLMResult) -> Optional[str]:
    """Pull Gemini thinking content out of the LLM response."""
    thoughts: List[str] = []
    generations = getattr(result, "generations", []) or []
    for generation_group in generations:
        if not generation_group:
            continue
        generation = generation_group[0]
        message = getattr(generation, "message", None)
        if not message:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    text = block.get("thinking") or block.get("text")
                    if text:
                        trimmed = text.strip()
                        if trimmed:
                            thoughts.append(trimmed)
    if thoughts:
        combined = "\n".join(thoughts)
        return combined[:2000]
    return None


MEMORY_MANAGER: MemorySessionManager = get_memory_session_manager()
LOG_MANAGER = get_log_manager()

app = FastAPI(title="Market Lens Realtime API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_session(authorization: str = Header(...)) -> AuthSession:
    prefix = "bearer "
    token = authorization.strip()
    if token.lower().startswith(prefix):
        token = token[len(prefix) :]
    session = AUTH_MANAGER.get_session(token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")
    return session


def ensure_session_owner(session_id: str, session: AuthSession) -> SessionMeta:
    meta = MEMORY_MANAGER.get_session_meta(session_id)
    if not meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if meta.owner not in (None, session.email):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if meta.owner is None:
        MEMORY_MANAGER.set_session_owner(session_id, session.email)
        meta = MEMORY_MANAGER.get_session_meta(session_id) or meta
    return meta


@app.post("/api/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if payload.guest:
        owner = f"guest-{secrets.token_hex(6)}"
        session = AUTH_MANAGER.create_session(email=owner, role="guest", display_name="guest")
        USER_STATE.reset_analysis_config(session.token)
        default_session = MEMORY_MANAGER.create_session(owner=owner)
        USER_STATE.set_active_session(session.token, default_session)
        return LoginResponse(
            token=session.token,
            email=owner,
            role=session.role,
            display_name="guest",
            active_session_id=default_session,
        )

    if not payload.email or not payload.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email and password required")

    if not validate_credentials(payload.email, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    normalized_email = payload.email.strip().lower()
    display_name = payload.email.strip()
    session = AUTH_MANAGER.create_session(email=normalized_email, role="member", display_name=display_name or normalized_email)
    USER_STATE.reset_analysis_config(session.token)
    existing_sessions = MEMORY_MANAGER.list_sessions(owner=normalized_email)
    active_session_id: Optional[str] = None
    if existing_sessions:
        active_session_id = existing_sessions[-1]
        USER_STATE.set_active_session(session.token, active_session_id)
    else:
        default_session = MEMORY_MANAGER.create_session(owner=normalized_email)
        USER_STATE.set_active_session(session.token, default_session)
        active_session_id = default_session
    return LoginResponse(
        token=session.token,
        email=normalized_email,
        role=session.role,
        display_name=session.display_name,
        active_session_id=active_session_id,
    )


@app.post("/api/logout")
def logout(session: AuthSession = Depends(get_current_session)) -> Dict[str, str]:
    AUTH_MANAGER.delete_session(session.token)
    USER_STATE.drop_session(session.token)
    return {"status": "ok"}


@app.get("/api/analysis-config", response_model=AnalysisConfigResponse)
def get_analysis_config(session: AuthSession = Depends(get_current_session)) -> AnalysisConfigResponse:
    config = USER_STATE.get_analysis_config(session.token)
    return AnalysisConfigResponse(config=config.copy())


@app.put("/api/analysis-config", response_model=AnalysisConfigResponse)
def update_analysis_config(
    payload: AnalysisConfigUpdate,
    session: AuthSession = Depends(get_current_session),
) -> AnalysisConfigResponse:
    data = {k: v for k, v in payload.dict().items() if v is not None}
    config = USER_STATE.update_analysis_config(session.token, data)
    return AnalysisConfigResponse(config=config.copy())


@app.post("/api/analysis-config/reset", response_model=AnalysisConfigResponse)
def reset_analysis_config(session: AuthSession = Depends(get_current_session)) -> AnalysisConfigResponse:
    config = USER_STATE.reset_analysis_config(session.token)
    return AnalysisConfigResponse(config=config.copy())


@app.get("/api/sessions", response_model=List[SessionResponse])
def list_sessions(session: AuthSession = Depends(get_current_session)) -> List[SessionResponse]:
    session_ids = MEMORY_MANAGER.list_sessions(owner=session.email)
    responses: List[SessionResponse] = []
    active_session = USER_STATE.get_active_session(session.token)
    for sid in session_ids:
        meta = MEMORY_MANAGER.get_session_meta(sid)
        if meta:
            responses.append(
                SessionResponse(
                    id=sid,
                    name=meta.name,
                    created_at=meta.created_at,
                    owner=meta.owner,
                    is_active=sid == active_session,
                )
            )
    return responses


@app.post("/api/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    session: AuthSession = Depends(get_current_session),
) -> SessionResponse:
    session_id = MEMORY_MANAGER.create_session(name=payload.name, owner=session.email)
    meta = MEMORY_MANAGER.get_session_meta(session_id)
    USER_STATE.set_active_session(session.token, session_id)
    return SessionResponse(id=session_id, name=meta.name, created_at=meta.created_at, owner=meta.owner, is_active=True)


@app.put("/api/sessions/{session_id}", response_model=SessionResponse)
def rename_session(
    session_id: str,
    payload: SessionRenameRequest,
    session: AuthSession = Depends(get_current_session),
) -> SessionResponse:
    meta = ensure_session_owner(session_id, session)
    MEMORY_MANAGER.rename_session(session_id, payload.name)
    updated = MEMORY_MANAGER.get_session_meta(session_id) or meta
    is_active = USER_STATE.get_active_session(session.token) == session_id
    return SessionResponse(
        id=session_id,
        name=updated.name,
        created_at=updated.created_at,
        owner=updated.owner,
        is_active=is_active,
    )


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, session: AuthSession = Depends(get_current_session)) -> Dict[str, str]:
    ensure_session_owner(session_id, session)
    MEMORY_MANAGER.delete_session(session_id)
    active = USER_STATE.get_active_session(session.token)
    if active == session_id:
        USER_STATE.set_active_session(session.token, None)
    return {"status": "deleted"}


@app.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str, session: AuthSession = Depends(get_current_session)) -> Dict[str, Any]:
    ensure_session_owner(session_id, session)
    messages = MEMORY_MANAGER.get_messages(session_id)
    payload = format_chat_history(messages, TOOL_DISPLAY_NAMES)
    return {"messages": payload}


@app.post("/api/sessions/{session_id}/activate")
def activate_session(session_id: str, session: AuthSession = Depends(get_current_session)) -> Dict[str, str]:
    ensure_session_owner(session_id, session)
    USER_STATE.set_active_session(session.token, session_id)
    return {"status": "ok"}


@app.get("/api/sessions/{session_id}/progress")
def get_session_progress(session_id: str, session: AuthSession = Depends(get_current_session)) -> Dict[str, Any]:
    ensure_session_owner(session_id, session)
    progress = MEMORY_MANAGER.get_progress(session_id)
    return {"progress": progress}


async def _forward_logs(websocket: WebSocket, log_queue: queue.Queue, session_id: str) -> None:
    """Forward log entries from queue to websocket and persist them."""
    manager_actor = "manager"
    manager_label = "Manager 主代理"
    last_thinking_messages: Dict[str, str] = {}
    last_invoked_tool: Optional[str] = None

    def _strip_think_blocks(text: str) -> str:
        """Remove <think>…</think> segments to avoid exposing raw chain-of-thought."""
        cleaned = text
        while True:
            start = cleaned.find("<think>")
            if start == -1:
                break
            end = cleaned.find("</think>", start + 7)
            if end == -1:
                cleaned = cleaned[:start]
                break
            cleaned = cleaned[:start] + cleaned[end + len("</think>") :]
        return cleaned.strip()

    async def _emit_manager_thinking(message: str, actor_key: str, label: str) -> None:
        try:
            await websocket.send_json(
                {
                    "type": "thinking_status",
                    "actor": actor_key,
                    "label": label,
                    "status": "start",
                }
            )
            await websocket.send_json(
                {
                    "type": "thinking_content",
                    "actor": actor_key,
                    "label": label,
                    "content": message,
                }
            )
        except WebSocketDisconnect:
            return

        async def _auto_stop() -> None:
            try:
                await asyncio.sleep(3.0)
                await websocket.send_json(
                    {
                        "type": "thinking_status",
                        "actor": actor_key,
                        "label": label,
                        "status": "stop",
                    }
                )
            except (WebSocketDisconnect, RuntimeError):
                return

        asyncio.create_task(_auto_stop())

    try:
        while True:
            try:
                entries = []
                while True:
                    entry = log_queue.get_nowait()
                    entries.append(entry)
            except queue.Empty:
                if entries:
                    for item in entries:
                        raw_message = item.get("message", "")
                        if not raw_message:
                            continue
                        raw_message = raw_message.strip()
                        if " | " in raw_message:
                            parts = raw_message.split(" | ", 2)
                            if len(parts) == 3:
                                raw_message = parts[2]
                        raw_message = ANSI_ESCAPE_RE.sub("", raw_message)
                        raw_message = raw_message.replace("\r", "").strip()
                        if not raw_message:
                            continue

                        lines = [line.strip() for line in raw_message.splitlines() if line.strip()]
                        if not lines:
                            continue

                        invoking_line = next((line for line in lines if line.startswith("Invoking:")), None)
                        if invoking_line:
                            match = re.search(r"Invoking:\s*`([^`]+)`", invoking_line)
                            last_invoked_tool = match.group(1).strip() if match else None

                        thinking_message: Optional[str] = None
                        progress_message: Optional[str] = None

                        responded_line = next(
                            (line for line in lines if line.lower().startswith("responded:")), None
                        )
                        if responded_line:
                            thinking_parts = [responded_line.split("responded:", 1)[1].strip()]
                            try:
                                responded_index = lines.index(responded_line)
                            except ValueError:
                                responded_index = -1
                            if responded_index != -1:
                                for extra_line in lines[responded_index + 1 :]:
                                    if extra_line.startswith("Invoking:"):
                                        continue
                                    if extra_line.lower().startswith("responded:"):
                                        break
                                    thinking_parts.append(extra_line)
                            thinking_message = "\n".join(part for part in thinking_parts if part)
                            progress_message = _strip_think_blocks(thinking_message)
                        else:
                            non_invoking_lines = [line for line in lines if not line.startswith("Invoking:")]
                            if not non_invoking_lines:
                                continue
                            progress_message = _strip_think_blocks("\n".join(non_invoking_lines))

                        progress_message = progress_message.strip()
                        if not progress_message:
                            continue

                        actor_key = last_invoked_tool or manager_actor
                        actor_label = manager_label
                        if actor_key != manager_actor:
                            actor_label = TOOL_DISPLAY_NAMES.get(actor_key, actor_key)

                        if thinking_message:
                            clean_thinking = progress_message
                            previous_thinking = last_thinking_messages.get(actor_key)
                            if clean_thinking and clean_thinking != previous_thinking:
                                last_thinking_messages[actor_key] = clean_thinking
                                if len(clean_thinking) > 800:
                                    clean_thinking = clean_thinking[:797] + "..."
                                await _emit_manager_thinking(clean_thinking, actor_key, actor_label)

                        message_to_store = progress_message
                        if len(message_to_store) > 800:
                            message_to_store = message_to_store[:797] + "..."
                        level = item.get("level")
                        tool_key = actor_key if thinking_message else "log"
                        try:
                            await _push_progress(
                                websocket,
                                session_id,
                                message=message_to_store,
                                tool=tool_key,
                                stage="thinking" if thinking_message else "log",
                                level=level,
                                timestamp=item.get("timestamp"),
                            )
                        except WebSocketDisconnect:
                            return
                        if thinking_message:
                            last_invoked_tool = None
                await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        pass


class WebSocketAgentCallback(AsyncCallbackHandler):
    """Bridge LangChain callback events to websocket messages."""

    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self._response_parts: List[str] = []
        self._tool_stack: List[str] = []
        self._llm_actor_stack: List[str] = []

    @staticmethod
    def _actor_label(actor_key: str) -> str:
        if actor_key == "manager":
            return "Manager 主代理"
        return TOOL_DISPLAY_NAMES.get(actor_key, actor_key)

    def _current_actor_key(self) -> str:
        return self._tool_stack[-1] if self._tool_stack else "manager"

    async def _send_thinking_status(
        self,
        actor_key: str,
        status: str,
        *,
        label: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "type": "thinking_status",
            "actor": actor_key,
            "label": label or self._actor_label(actor_key),
            "status": status,
        }
        if message:
            payload["message"] = message
        await self.websocket.send_json(payload)

    async def on_llm_start(self, *args: Any, **kwargs: Any) -> None:
        self._response_parts = []
        await self.websocket.send_json({"type": "status", "message": "模型生成中..."})
        actor_key = self._current_actor_key()
        self._llm_actor_stack.append(actor_key)
        await self._send_thinking_status(actor_key, "start")

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        self._response_parts.append(token)
        await self.websocket.send_json({"type": "token", "token": token})

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        await self.websocket.send_json({"type": "status", "message": "生成完成"})
        actor_key = self._llm_actor_stack.pop() if self._llm_actor_stack else "manager"
        label = self._actor_label(actor_key)
        thinking_text = _extract_thinking_text(response)
        if thinking_text:
            await self.websocket.send_json(
                {
                    "type": "thinking_content",
                    "actor": actor_key,
                    "label": label,
                    "content": thinking_text,
                }
            )
        await self._send_thinking_status(actor_key, "stop", label=label)

    async def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        actor_key = self._llm_actor_stack.pop() if self._llm_actor_stack else "manager"
        await self._send_thinking_status(
            actor_key,
            "error",
            label=self._actor_label(actor_key),
            message=str(error),
        )

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "工具调用")
        self._tool_stack.append(tool_name)
        template = PROGRESS_TEMPLATES.get(tool_name, {})
        label = TOOL_DISPLAY_NAMES.get(tool_name, tool_name.upper())
        message = template.get("start") or f"[{label}] 正在执行…"
        await _push_progress(
            self.websocket,
            self.session_id,
            message=message,
            tool=tool_name,
            stage="start",
        )

    async def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        tool_name = self._tool_stack[-1] if self._tool_stack else None
        template = PROGRESS_TEMPLATES.get(tool_name or "", {})
        label = TOOL_DISPLAY_NAMES.get(tool_name or "", "工具")
        message = template.get("end") or f"[{label}] 阶段完成 ✅"
        await _push_progress(
            self.websocket,
            self.session_id,
            message=message,
            tool=tool_name,
            stage="end",
        )
        if tool_name and self._tool_stack and self._tool_stack[-1] == tool_name:
            self._tool_stack.pop()
        elif tool_name in self._tool_stack:
            self._tool_stack.remove(tool_name)

    async def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        tool_name = None
        if self._tool_stack:
            tool_name = self._tool_stack.pop()
        tool_name = tool_name or kwargs.get("name")
        label = TOOL_DISPLAY_NAMES.get(tool_name or "", tool_name or "TOOL")
        await _push_progress(
            self.websocket,
            self.session_id,
            message=f"[{label}] 执行失败：{error}",
            tool=tool_name,
            stage="error",
        )

    def get_response_text(self) -> str:
        return "".join(self._response_parts).strip()


@app.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(..., description="Bearer token obtained from /api/login"),
) -> None:
    session = AUTH_MANAGER.get_session(token)
    if not session:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        ensure_session_owner(session_id, session)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    memory = MEMORY_MANAGER.get_memory(session_id)

    log_queue = LOG_MANAGER.create_session(session_id)
    log_task = asyncio.create_task(_forward_logs(websocket, log_queue, session_id))

    try:
        while True:
            event = await websocket.receive_json()
            if event.get("type") != "user_message":
                continue

            user_input = event.get("content", "").strip()
            if not user_input:
                await websocket.send_json({"type": "error", "message": "请输入有效的问题"})
                continue

            callback = WebSocketAgentCallback(websocket, session_id)
            analysis_config = USER_STATE.get_analysis_config(token)
            enabled_sections = [key for key, enabled in analysis_config.items() if enabled]
            if enabled_sections:
                summary = "、".join(ANALYSIS_LABELS.get(key, key) for key in enabled_sections)
                manager_msg = f"[MANAGER] 正在调度 Analyst 分析 {summary} 维度，并整合下游代理…"
            else:
                manager_msg = "[MANAGER] 正在调度子代理执行请求…"
            await _push_progress(
                websocket,
                session_id,
                message=manager_msg,
                tool="manager",
                stage="start",
            )
            agent = build_main_agent(config=analysis_config, memory=memory)

            try:
                result = await agent.ainvoke({"input": user_input}, callbacks=[callback])  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json({"type": "error", "message": f"代理执行失败：{exc}"})
                continue

            response_text = callback.get_response_text() or result.get("output", "")
            history = MEMORY_MANAGER.get_messages(session_id)
            formatted_history = format_chat_history(history, TOOL_DISPLAY_NAMES)
            await websocket.send_json({"type": "final", "content": response_text, "messages": formatted_history})
            await _push_progress(
                websocket,
                session_id,
                message="[MANAGER] 分析完成 🎯",
                tool="manager",
                stage="complete",
            )
    except WebSocketDisconnect:
        pass
    finally:
        log_task.cancel()
        LOG_MANAGER.cleanup_session(session_id)
        try:
            await log_task
        except asyncio.CancelledError:
            pass
