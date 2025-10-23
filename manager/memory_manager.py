import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from langchain.memory import ConversationBufferMemory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


def _safe_serialize(value, limit: int = 1200) -> str:
    """Serialize tool inputs/outputs to compact text."""
    try:
        serialized = json.dumps(value, ensure_ascii=False)
    except TypeError:
        serialized = str(value)
    if len(serialized) > limit:
        return serialized[: limit - 3] + "..."
    return serialized


def _timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _strip_empty(mapping: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in mapping.items() if v not in (None, {}, [], "")}


class StructuredChatMessageHistory(BaseChatMessageHistory):
    """Persist chat history and decisions in a readable JSON structure."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._history: List[Dict[str, Any]] = []
        self._decisions: List[Dict[str, Any]] = []
        self._progress: List[Dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(payload, dict):
            if "history" in payload or "decisions" in payload:
                self._history = payload.get("history", [])
                self._decisions = payload.get("decisions", [])
                self._progress = payload.get("progress", [])
            elif "messages" in payload:
                self._history = [
                    self._legacy_entry_to_record(item) for item in payload.get("messages", [])
                ]
                self._decisions = []
                self._progress = []
        elif isinstance(payload, list):
            self._history = [self._legacy_entry_to_record(item) for item in payload]
            self._decisions = []
            self._progress = []
        else:
            self._history = []
            self._decisions = []
            self._progress = []

        # Always persist back using the new structured format for readability
        self._save()

    def _save(self) -> None:
        payload = {
            "history": self._history,
            "decisions": self._decisions,
            "progress": self._progress,
        }
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # BaseChatMessageHistory interface
    # ------------------------------------------------------------------ #
    @property
    def messages(self) -> List[BaseMessage]:
        return [self._record_to_message(record) for record in self._history]

    def add_message(self, message: BaseMessage) -> None:
        record = self._message_to_record(message)
        self._history.append(record)
        self._save()

    def clear(self) -> None:
        self._history = []
        self._decisions = []
        self._progress = []
        self._save()

    # ------------------------------------------------------------------ #
    # Decision logging API
    # ------------------------------------------------------------------ #
    def add_decision(self, decision: Dict[str, Any]) -> None:
        decision = decision.copy()
        decision.setdefault("timestamp", _timestamp())
        self._decisions.append(decision)
        self._save()

    def get_decisions(self) -> List[Dict[str, Any]]:
        return list(self._decisions)

    # ------------------------------------------------------------------ #
    # Progress logging API
    # ------------------------------------------------------------------ #
    def add_progress(self, entry: Dict[str, Any]) -> None:
        record = entry.copy()
        record.setdefault("timestamp", _timestamp())
        self._progress.append(record)
        if len(self._progress) > 500:
            self._progress = self._progress[-500:]
        self._save()

    def get_progress(self) -> List[Dict[str, Any]]:
        return list(self._progress)

    # ------------------------------------------------------------------ #
    # Message serialization helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _message_to_record(message: BaseMessage) -> Dict[str, Any]:
        base_record: Dict[str, Any] = {
            "role": message.type,
            "content": message.content,
            "timestamp": _timestamp(),
        }

        if message.additional_kwargs:
            base_record["additional_kwargs"] = message.additional_kwargs
        if message.response_metadata:
            base_record["response_metadata"] = message.response_metadata
        if message.name:
            base_record["name"] = message.name
        if message.id:
            base_record["id"] = message.id

        if isinstance(message, AIMessage):
            if message.tool_calls:
                base_record["tool_calls"] = message.tool_calls
        return base_record

    @staticmethod
    def _record_to_message(record: Dict[str, Any]) -> BaseMessage:
        role = record.get("role", "human")
        content = record.get("content", "")
        common_kwargs = {
            "additional_kwargs": record.get("additional_kwargs") or {},
            "response_metadata": record.get("response_metadata") or {},
            "name": record.get("name"),
            "id": record.get("id"),
        }

        if role == "human":
            return HumanMessage(content=content, **_strip_empty(common_kwargs))
        if role == "ai":
            extra = common_kwargs.copy()
            if "tool_calls" in record:
                extra["tool_calls"] = record["tool_calls"]
            return AIMessage(content=content, **_strip_empty(extra))
        if role == "system":
            return SystemMessage(content=content, **_strip_empty(common_kwargs))
        # Default fallback to system message for unknown role
        fallback = {
            "role": role,
            "content": content,
            "metadata": record.get("additional_kwargs", {}),
        }
        return SystemMessage(content=json.dumps(fallback, ensure_ascii=False))

    @staticmethod
    def _legacy_entry_to_record(entry: Dict[str, Any]) -> Dict[str, Any]:
        """Convert legacy LangChain message dict into the new record format."""
        entry_type = entry.get("type", "")
        data = entry.get("data", {})
        content = data.get("content") or ""
        record: Dict[str, Any] = {
            "role": data.get("type", entry_type),
            "content": content,
            "timestamp": data.get("timestamp") or _timestamp(),
        }

        if record["role"] == "tool":
            record["role"] = "system"

        for key in ("additional_kwargs", "response_metadata", "name", "id"):
            if data.get(key):
                record[key] = data[key]

        if "tool_calls" in data and data["tool_calls"]:
            record["tool_calls"] = data["tool_calls"]
        if "tool_call_id" in data:
            record["tool_call_id"] = data["tool_call_id"]

        return record


class ToolAwareConversationMemory(ConversationBufferMemory):
    """Conversation memory that also records tool call metadata as system messages."""

    def load_memory_variables(self, inputs: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = super().load_memory_variables(inputs or {})
        return self._filter_tool_events(data)

    async def aload_memory_variables(self, inputs: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = await super().aload_memory_variables(inputs or {})
        return self._filter_tool_events(data)

    def _filter_tool_events(self, data: Dict[str, Any]) -> Dict[str, Any]:
        memory_key = getattr(self, "memory_key", "history")
        messages = data.get(memory_key)
        if isinstance(messages, list):
            filtered = [
                message
                for message in messages
                if not (
                    isinstance(message, SystemMessage)
                    and message.additional_kwargs.get("tool_event")
                )
            ]
            data[memory_key] = filtered
        return data

    def save_context(
        self, inputs: Dict[str, str], outputs: Dict[str, str], *args, **kwargs
    ) -> None:
        # Extract intermediate steps before the base class mutates outputs.
        intermediate_steps = outputs.pop("intermediate_steps", [])
        agent_output = outputs.get(getattr(self, "output_key", "output"))
        super().save_context(inputs, outputs, *args, **kwargs)

        if not intermediate_steps:
            if hasattr(self.chat_memory, "add_decision"):
                self.chat_memory.add_decision(
                    {
                        "input": inputs.get(getattr(self, "input_key", "input")),
                        "output": agent_output,
                        "tools": [],
                    }
                )
            return

        for action, observation in intermediate_steps:
            record = {
                "tool": getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", None),
                "log": getattr(action, "log", ""),
                "output": observation,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            summary_lines = [
                f"🔧 工具调用：{record['tool']}",
                f"➡️ 输入：{_safe_serialize(record['input'])}",
                f"⬅️ 输出：{_safe_serialize(record['output'])}",
            ]
            if record["log"]:
                summary_lines.append(f"📝 日志：{_safe_serialize(record['log'])}")

            record["tool_call_id"] = getattr(action, "tool_call_id", None)
            message = SystemMessage(
                content="\n".join(summary_lines),
                additional_kwargs={"tool_event": record},
            )
            self.chat_memory.add_message(message)

        if hasattr(self.chat_memory, "add_decision"):
            tools = [
                {
                    "tool": getattr(action, "tool", "unknown"),
                    "input": getattr(action, "tool_input", None),
                    "output": observation,
                    "log": getattr(action, "log", ""),
                    "tool_call_id": getattr(action, "tool_call_id", None),
                }
                for action, observation in intermediate_steps
            ]
            self.chat_memory.add_decision(
                {
                    "input": inputs.get(getattr(self, "input_key", "input")),
                    "output": agent_output,
                    "tools": tools,
                }
            )

    async def asave_context(
        self, inputs: Dict[str, str], outputs: Dict[str, str], *args, **kwargs
    ) -> None:
        intermediate_steps = outputs.pop("intermediate_steps", [])
        agent_output = outputs.get(getattr(self, "output_key", "output"))
        await super().asave_context(inputs, outputs, *args, **kwargs)

        if not intermediate_steps:
            if hasattr(self.chat_memory, "add_decision"):
                self.chat_memory.add_decision(
                    {
                        "input": inputs.get(getattr(self, "input_key", "input")),
                        "output": agent_output,
                        "tools": [],
                    }
                )
            return

        for action, observation in intermediate_steps:
            record = {
                "tool": getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", None),
                "log": getattr(action, "log", ""),
                "output": observation,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            summary_lines = [
                f"🔧 工具调用：{record['tool']}",
                f"➡️ 输入：{_safe_serialize(record['input'])}",
                f"⬅️ 输出：{_safe_serialize(record['output'])}",
            ]
            if record["log"]:
                summary_lines.append(f"📝 日志：{_safe_serialize(record['log'])}")

            record["tool_call_id"] = getattr(action, "tool_call_id", None)
            message = SystemMessage(
                content="\n".join(summary_lines),
                additional_kwargs={"tool_event": record},
            )
            self.chat_memory.add_message(message)

        if hasattr(self.chat_memory, "add_decision"):
            tools = [
                {
                    "tool": getattr(action, "tool", "unknown"),
                    "input": getattr(action, "tool_input", None),
                    "output": observation,
                    "log": getattr(action, "log", ""),
                    "tool_call_id": getattr(action, "tool_call_id", None),
                }
                for action, observation in intermediate_steps
            ]
            self.chat_memory.add_decision(
                {
                    "input": inputs.get(getattr(self, "input_key", "input")),
                    "output": agent_output,
                    "tools": tools,
                }
            )


@dataclass
class SessionMeta:
    name: str
    created_at: str
    owner: Optional[str] = None


class MemorySessionManager:
    """Manage LangChain chat memories across named sessions."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(__file__).parent / "memory_sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.storage_dir / "meta.json"
        self._memory_cache: Dict[str, ToolAwareConversationMemory] = {}
        self._meta = self._load_meta()

    # ------------------------------------------------------------------ #
    # Meta management helpers
    # ------------------------------------------------------------------ #
    def _load_meta(self) -> Dict[str, SessionMeta]:
        if not self.meta_path.exists():
            return {}
        try:
            with open(self.meta_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}
        meta: Dict[str, SessionMeta] = {}
        for session_id, info in payload.items():
            meta[session_id] = SessionMeta(
                name=info.get("name", session_id),
                created_at=info.get("created_at", datetime.utcnow().isoformat() + "Z"),
                owner=info.get("owner"),
            )
        return meta

    def _save_meta(self) -> None:
        payload = {}
        for session_id, meta in self._meta.items():
            payload[session_id] = {
                "name": meta.name,
                "created_at": meta.created_at,
            }
            if meta.owner:
                payload[session_id]["owner"] = meta.owner
        with open(self.meta_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def _generate_session_id(self) -> str:
        return datetime.utcnow().strftime("session-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]

    def _generate_default_name(self) -> str:
        prefix = "对话 "
        existing = {meta.name for meta in self._meta.values() if meta.name.startswith(prefix)}
        index = 1
        while f"{prefix}{index}" in existing:
            index += 1
        return f"{prefix}{index}"

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def list_sessions(self, owner: Optional[str] = None) -> List[str]:
        session_ids = self._meta.keys()
        if owner is not None:
            session_ids = [
                sid for sid, meta in self._meta.items() if meta.owner in (None, owner)
            ]

        return sorted(
            session_ids,
            key=lambda sid: self._meta[sid].created_at if sid in self._meta else "",
        )

    def get_session_name(self, session_id: str) -> str:
        return self._meta.get(session_id, SessionMeta(session_id, "")).name

    def rename_session(self, session_id: str, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name or session_id not in self._meta:
            return
        self._meta[session_id].name = new_name
        self._save_meta()

    def create_session(self, name: Optional[str] = None, owner: Optional[str] = None) -> str:
        session_id = self._generate_session_id()
        session_name = name.strip() if name else self._generate_default_name()
        self._meta[session_id] = SessionMeta(
            name=session_name,
            created_at=datetime.utcnow().isoformat() + "Z",
            owner=owner,
        )
        self._save_meta()
        return session_id

    def get_session_owner(self, session_id: str) -> Optional[str]:
        meta = self._meta.get(session_id)
        return meta.owner if meta else None

    def get_session_meta(self, session_id: str) -> Optional[SessionMeta]:
        return self._meta.get(session_id)

    def set_session_owner(self, session_id: str, owner: Optional[str]) -> None:
        if session_id in self._meta:
            self._meta[session_id].owner = owner
            self._save_meta()

    def delete_session(self, session_id: str) -> None:
        if session_id in self._memory_cache:
            del self._memory_cache[session_id]

        history_path = self.storage_dir / f"{session_id}.json"
        if history_path.exists():
            history_path.unlink()

        if session_id in self._meta:
            del self._meta[session_id]
            self._save_meta()

    def clear(self) -> None:
        for session_id in list(self._meta.keys()):
            self.delete_session(session_id)

    def get_memory(self, session_id: str) -> ToolAwareConversationMemory:
        if session_id not in self._memory_cache:
            history_path = self.storage_dir / f"{session_id}.json"
            chat_history = StructuredChatMessageHistory(str(history_path))
            memory = ToolAwareConversationMemory(
                memory_key="messages",
                return_messages=True,
                input_key="input",
                chat_memory=chat_history,
            )
            self._memory_cache[session_id] = memory
        return self._memory_cache[session_id]

    def get_messages(self, session_id: str) -> List[BaseMessage]:
        memory = self.get_memory(session_id)
        return list(memory.chat_memory.messages)

    def get_decisions(self, session_id: str) -> List[Dict[str, Any]]:
        memory = self.get_memory(session_id)
        history = getattr(memory.chat_memory, "get_decisions", None)
        if callable(history):
            return history()
        return []

    def append_progress(self, session_id: str, entry: Dict[str, Any]) -> None:
        memory = self.get_memory(session_id)
        history = getattr(memory.chat_memory, "add_progress", None)
        if callable(history):
            history(entry)

    def get_progress(self, session_id: str) -> List[Dict[str, Any]]:
        memory = self.get_memory(session_id)
        history = getattr(memory.chat_memory, "get_progress", None)
        if callable(history):
            return history()
        return []


_SESSION_MANAGER: Optional[MemorySessionManager] = None


def get_memory_session_manager() -> MemorySessionManager:
    global _SESSION_MANAGER
    if _SESSION_MANAGER is None:
        _SESSION_MANAGER = MemorySessionManager()
    return _SESSION_MANAGER
