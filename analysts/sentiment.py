# analysts/sentiment.py
"""将 sentiment 工具导出给上层使用。

此处直接复用 `analysts/X_search/sentiment.py` 中已实现的 LangChain StructuredTool：
- get_sentiment: 与 fundamentals 同风格的工具封装（async coroutine）
"""

try:
    from analysts.X_search.sentiment import get_sentiment  # type: ignore
except Exception:
    from analysts.X_search.sentiment import get_sentiment  # type: ignore

__all__ = [
    "get_sentiment",
]
