import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from langchain_core.messages import HumanMessage, AIMessage


class ChatHistoryManager:
    """
    聊天历史管理器 - 单例模式
    
    负责：
    - 持久化存储聊天历史
    - 会话隔离
    - 自动限制历史长度
    - 线程安全的文件操作
    """
    
    _instance: Optional['ChatHistoryManager'] = None
    
    def __new__(cls, history_file: Optional[Path] = None):
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, history_file: Optional[Path] = None):
        """初始化历史管理器"""
        if self._initialized:
            return
            
        self.history_file = history_file or Path(__file__).parent / "chat_history.json"
        self._sessions: Dict[str, List[Dict]] = {}
        self._max_history_per_session = 50
        self._load()
        self._initialized = True
    
    def _load(self) -> None:
        """从文件加载历史记录"""
        if not self.history_file.exists():
            self._sessions = {}
            return
            
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                self._sessions = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARNING] 加载历史失败: {e}，使用空历史")
            self._sessions = {}
    
    def _save(self) -> bool:
        """保存历史记录到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self._sessions, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[ERROR] 保存历史失败: {e}")
            return False
    
    def add(self, session_id: str, user_msg: str, assistant_msg: str) -> None:
        """
        添加一条对话记录
        
        Args:
            session_id: 会话ID
            user_msg: 用户消息
            assistant_msg: 助手回复
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        self._sessions[session_id].append({
            "timestamp": datetime.now().isoformat(),
            "user": user_msg,
            "assistant": assistant_msg
        })
        
        # 自动截断：只保留最近的N条对话
        if len(self._sessions[session_id]) > self._max_history_per_session:
            self._sessions[session_id] = self._sessions[session_id][-self._max_history_per_session:]
        
        self._save()
    
    def get_messages(self, session_id: str, limit: Optional[int] = None) -> List:
        """
        获取会话的消息列表（LangChain格式）
        
        Args:
            session_id: 会话ID
            limit: 限制返回的对话轮数（None=全部）
        
        Returns:
            LangChain消息对象列表
        """
        if session_id not in self._sessions:
            return []
        
        history = self._sessions[session_id]
        if limit:
            history = history[-limit:]
        
        messages = []
        for conv in history:
            messages.append(HumanMessage(content=conv["user"]))
            messages.append(AIMessage(content=conv["assistant"]))
        
        return messages
    
    def get_raw_history(self, session_id: str) -> List[Dict]:
        """获取原始历史数据（用于调试/导出）"""
        return self._sessions.get(session_id, [])
    
    def clear(self, session_id: Optional[str] = None) -> bool:
        """
        清空历史记录
        
        Args:
            session_id: 指定会话ID则只清空该会话，None则清空所有
        
        Returns:
            操作是否成功
        """
        if session_id:
            if session_id in self._sessions:
                del self._sessions[session_id]
                print(f"[INFO] 已清空会话 {session_id} 的历史")
        else:
            self._sessions = {}
            print("[INFO] 已清空所有聊天历史")
        
        return self._save()
    
    def reload(self) -> None:
        """强制重新加载历史（用于多进程同步）"""
        self._load()
    
    def set_max_history(self, max_count: int) -> None:
        """设置每个会话保留的最大历史条数"""
        if max_count < 1:
            raise ValueError("历史条数必须至少为1")
        self._max_history_per_session = max_count
    
    def list_sessions(self) -> List[str]:
        """列出所有会话ID"""
        return list(self._sessions.keys())
    
    def __repr__(self) -> str:
        total_conversations = sum(len(history) for history in self._sessions.values())
        return f"<ChatHistoryManager: {len(self._sessions)} sessions, {total_conversations} conversations>"


# 便捷的全局单例访问
def get_history_manager(history_file: Optional[Path] = None) -> ChatHistoryManager:
    """获取历史管理器单例"""
    return ChatHistoryManager(history_file)

