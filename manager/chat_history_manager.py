import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage


class ChatHistoryManager:
    """
    聊天历史管理器 - 单例模式

    负责：
    - 持久化存储聊天历史
    - 会话隔离与命名
    - 自动限制历史长度
    - 线程安全的文件操作
    """

    _instance: Optional["ChatHistoryManager"] = None

    def __new__(cls, history_file: Optional[Path] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, history_file: Optional[Path] = None):
        if self._initialized:
            return

        self.history_file = history_file or Path(__file__).parent / "chat_history.json"
        self._sessions: Dict[str, List[Dict]] = {}
        self._names: Dict[str, str] = {}
        self._order: List[str] = []
        self._max_history_per_session = 50
        self._load()
        self._initialized = True

    # ------------------------------------------------------------------ #
    # 内部工具方法
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        """从文件加载历史记录与会话名称。"""
        if not self.history_file.exists():
            self._sessions = {}
            self._names = {}
            self._order = []
            return

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            print(f"[WARNING] 加载历史失败: {exc}，使用空历史")
            self._sessions = {}
            self._names = {}
            self._order = []
            return

        if isinstance(data, dict) and "sessions" in data:
            self._sessions = data.get("sessions", {})
            meta = data.get("_meta", {})
            self._names = meta.get("names", {})
            self._order = meta.get("order", list(self._sessions.keys()))
        elif isinstance(data, dict):
            # 兼容旧格式：键即为会话名称
            self._sessions = data
            self._names = {sid: sid for sid in self._sessions.keys()}
            self._order = list(self._sessions.keys())
            self._save()
        else:
            self._sessions = {}
            self._names = {}
            self._order = []

        valid_ids = set(self._sessions.keys())
        self._names = {sid: self._names.get(sid, sid) for sid in valid_ids}
        self._order = [sid for sid in self._order if sid in valid_ids]
        for sid in valid_ids:
            if sid not in self._order:
                self._order.append(sid)

    def _save(self) -> bool:
        """持久化所有会话内容与名称。"""
        payload = {
            "sessions": self._sessions,
            "_meta": {
                "names": self._names,
                "order": self._order,
            },
        }
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return True
        except IOError as exc:
            print(f"[ERROR] 保存历史失败: {exc}")
            return False

    def _generate_default_name(self) -> str:
        """生成默认会话名称：对话 N。"""
        prefix = "对话 "
        indices = []
        for name in self._names.values():
            if name.startswith(prefix):
                try:
                    indices.append(int(name[len(prefix) :].strip()))
                except ValueError:
                    continue
        next_index = max(indices, default=0) + 1
        return f"{prefix}{next_index}"

    def _ensure_unique_name(self, base_name: str, exclude: Optional[str] = None) -> str:
        """确保名称唯一，如冲突则追加 (n) 后缀。"""
        existing = {sid: name for sid, name in self._names.items() if sid != exclude}
        if base_name not in existing.values():
            return base_name

        suffix = 2
        while True:
            candidate = f"{base_name} ({suffix})"
            if candidate not in existing.values():
                return candidate
            suffix += 1

    # ------------------------------------------------------------------ #
    # 公共方法
    # ------------------------------------------------------------------ #
    def add(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """追加对话轮次，并保证会话存在。"""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
            self._names.setdefault(session_id, self._generate_default_name())
            self._order.append(session_id)

        self._sessions[session_id].append(
            {
                "timestamp": datetime.now().isoformat(),
                "user": user_msg,
                "assistant": assistant_msg,
            }
        )

        if len(self._sessions[session_id]) > self._max_history_per_session:
            self._sessions[session_id] = self._sessions[session_id][
                -self._max_history_per_session :
            ]

        self._save()

    def get_messages(self, session_id: str, limit: Optional[int] = None) -> List:
        """以 LangChain 消息格式返回指定会话历史。"""
        history = self._sessions.get(session_id, [])
        if limit:
            history = history[-limit:]

        messages = []
        for conv in history:
            messages.append(HumanMessage(content=conv["user"]))
            messages.append(AIMessage(content=conv["assistant"]))
        return messages

    def get_raw_history(self, session_id: str) -> List[Dict]:
        """返回原始对话记录列表。"""
        return self._sessions.get(session_id, [])

    def create_session(self, session_name: Optional[str] = None) -> str:
        """创建新的会话并返回其 ID。"""
        session_id = datetime.now().strftime("session-%Y%m%d-%H%M%S-%f")
        name = session_name or self._generate_default_name()
        name = self._ensure_unique_name(name)

        self._sessions[session_id] = []
        self._names[session_id] = name
        self._order.append(session_id)
        self._save()
        return session_id

    def rename_session(self, session_id: str, new_name: str) -> None:
        """重命名会话；忽略空名称和不存在的会话。"""
        new_name = new_name.strip()
        if not new_name or session_id not in self._sessions:
            return
        self._names[session_id] = self._ensure_unique_name(new_name, exclude=session_id)
        self._save()

    def get_session_name(self, session_id: str) -> str:
        """获取会话名称，若不存在则返回 ID。"""
        return self._names.get(session_id, session_id)

    def clear(self, session_id: Optional[str] = None) -> bool:
        """清空指定会话或全部会话。"""
        if session_id:
            if session_id in self._sessions:
                del self._sessions[session_id]
            if session_id in self._names:
                del self._names[session_id]
            if session_id in self._order:
                self._order.remove(session_id)
        else:
            self._sessions = {}
            self._names = {}
            self._order = []

        return self._save()

    def reload(self) -> None:
        """重新加载历史记录（用于多进程同步）。"""
        self._load()

    def set_max_history(self, max_count: int) -> None:
        """设置每个会话保留的最大轮数。"""
        if max_count < 1:
            raise ValueError("历史条数必须至少为 1")
        self._max_history_per_session = max_count

    def list_sessions(self) -> List[str]:
        """返回所有会话 ID，遵循创建顺序。"""
        return list(self._order)

    def __repr__(self) -> str:
        total_conversations = sum(len(history) for history in self._sessions.values())
        return f"<ChatHistoryManager: {len(self._sessions)} sessions, {total_conversations} conversations>"


def get_history_manager(history_file: Optional[Path] = None) -> ChatHistoryManager:
    """获取历史管理器单例。"""
    return ChatHistoryManager(history_file)
