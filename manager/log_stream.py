"""
Real-time log streaming system.
Thread-safe with multi-consumer support.
"""
import logging
import queue
import threading
import sys
from typing import Dict, Optional
from datetime import datetime


class StdoutCapture:
    """Capture stdout/stderr output into a queue."""
    
    def __init__(self, log_queue: queue.Queue, original_stream):
        self.log_queue = log_queue
        self.original_stream = original_stream
    
    def write(self, text: str):
        # Mirror output to the original stream for CLI visibility
        self.original_stream.write(text)
        self.original_stream.flush()
        
        # Push to queue (skip blank lines)
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
        # Delegate other attributes to the original stream
        return getattr(self.original_stream, name)


class LogStreamHandler(logging.Handler):
    """Custom logging handler that pushes records to the queue."""
    
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
            pass  # Drop when the queue is full to avoid blocking


class LogStreamManager:
    """Singleton log-stream manager."""
    
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
        """Create a log queue for the session and redirect stdout."""
        if session_id not in self.sessions:
            log_queue = queue.Queue(maxsize=1000)
            
            # Attach logging handler
            handler = LogStreamHandler(log_queue)
            handler.setLevel(logging.INFO)
            self.sessions[session_id] = log_queue
            self.handlers[session_id] = handler
            self.root_logger.addHandler(handler)
            
            # Redirect stdout (capture print output)
            stdout_capture = StdoutCapture(log_queue, self.original_stdout)
            self.stdout_captures[session_id] = stdout_capture
            sys.stdout = stdout_capture
        
        return self.sessions[session_id]
    
    def get_logs(self, session_id: str, max_items: int = 100) -> list:
        """Retrieve logs without blocking."""
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
        """Clean up session logs and restore stdout."""
        # Restore original stdout
        if session_id in self.stdout_captures:
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr
            del self.stdout_captures[session_id]
        
        # Remove handler
        if session_id in self.handlers:
            self.root_logger.removeHandler(self.handlers[session_id])
            del self.handlers[session_id]
        
        # Remove queue reference
        if session_id in self.sessions:
            del self.sessions[session_id]


# Configure baseline logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Global singleton instance
_log_manager = LogStreamManager()


def get_log_manager() -> LogStreamManager:
    return _log_manager
