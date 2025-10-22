"""
实时日志流式传输系统
线程安全，支持多消费者
"""
import logging
import queue
import threading
import sys
from typing import Dict, Optional
from datetime import datetime


class StdoutCapture:
    """捕获 stdout/stderr 输出到队列"""
    
    def __init__(self, log_queue: queue.Queue, original_stream):
        self.log_queue = log_queue
        self.original_stream = original_stream
    
    def write(self, text: str):
        # 同时输出到原始流（保持命令行可见）
        self.original_stream.write(text)
        self.original_stream.flush()
        
        # 推送到队列（去除空行）
        text = text.strip()
        if text:
            try:
                self.log_queue.put_nowait({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'INFO',
                    'message': text
                })
            except queue.Full:
                pass
    
    def flush(self):
        self.original_stream.flush()
    
    def isatty(self):
        return self.original_stream.isatty()
    
    def __getattr__(self, name):
        # 代理其他方法到原始流
        return getattr(self.original_stream, name)


class LogStreamHandler(logging.Handler):
    """自定义日志处理器，将日志推送到队列"""
    
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
    
    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put_nowait({
                'timestamp': datetime.now().isoformat(),
                'level': record.levelname,
                'message': msg
            })
        except queue.Full:
            pass  # 队列满了就丢弃，避免阻塞


class LogStreamManager:
    """日志流管理器 - 单例模式"""
    
    _instance: Optional['LogStreamManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.sessions: Dict[str, queue.Queue] = {}
            self.handlers: Dict[str, LogStreamHandler] = {}
            self.stdout_captures: Dict[str, StdoutCapture] = {}
            self.root_logger = logging.getLogger()
            self.original_stdout = sys.stdout
            self.original_stderr = sys.stderr
            self.initialized = True
    
    def create_session(self, session_id: str) -> queue.Queue:
        """为会话创建日志队列并重定向 stdout"""
        if session_id not in self.sessions:
            log_queue = queue.Queue(maxsize=1000)
            
            # 添加 logging handler
            handler = LogStreamHandler(log_queue)
            handler.setLevel(logging.INFO)
            self.sessions[session_id] = log_queue
            self.handlers[session_id] = handler
            self.root_logger.addHandler(handler)
            
            # 重定向 stdout（捕获 print 输出）
            stdout_capture = StdoutCapture(log_queue, self.original_stdout)
            self.stdout_captures[session_id] = stdout_capture
            sys.stdout = stdout_capture
        
        return self.sessions[session_id]
    
    def get_logs(self, session_id: str, max_items: int = 100) -> list:
        """非阻塞获取日志"""
        if session_id not in self.sessions:
            return []
        
        logs = []
        q = self.sessions[session_id]
        
        try:
            while len(logs) < max_items:
                logs.append(q.get_nowait())
        except queue.Empty:
            pass
        
        return logs
    
    def cleanup_session(self, session_id: str):
        """清理会话日志并恢复 stdout"""
        # 恢复原始 stdout
        if session_id in self.stdout_captures:
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr
            del self.stdout_captures[session_id]
        
        # 移除 handler
        if session_id in self.handlers:
            self.root_logger.removeHandler(self.handlers[session_id])
            del self.handlers[session_id]
        
        # 清理队列
        if session_id in self.sessions:
            del self.sessions[session_id]


# 配置基础 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 全局单例
_log_manager = LogStreamManager()


def get_log_manager() -> LogStreamManager:
    return _log_manager

