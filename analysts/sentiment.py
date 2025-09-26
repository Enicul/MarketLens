# analysts/sentiment.py
"""导出与 Agent 兼容的 sentiment 工具。

本模块将 `analysts.X_search.sentonent.get_sentiment_func` 封装为 LangChain 的
`StructuredTool`，名称仍为 `get_sentiment`，以保持上层 Agent 与既有调用不变。
"""

from langchain.tools import StructuredTool

try:
    from analysts.X_search.sentiment import get_sentiment_func  # type: ignore
except Exception:
    from analysts.X_search.sentiment import get_sentiment_func  # type: ignore


get_sentiment = StructuredTool.from_function(
    func=get_sentiment_func,
    coroutine=get_sentiment_func,
    name="get_sentiment",
    description=(
        "Get recent tweet samples and basic interaction stats from X/Twitter for a given stock ticker. "
        "Returns a JSON string. Useful for gauging short-term market sentiment signals."
    ),
)


__all__ = ["get_sentiment"]
