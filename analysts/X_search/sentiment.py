import json
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path

# 与 fundamentals.py 保持一致的导入方式
try:
    from langchain.tools import StructuredTool
except Exception as _e:  # pragma: no cover
    StructuredTool = None  # type: ignore

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore
    Field = lambda default=None, **kwargs: default  # type: ignore

try:
    # 相对导入本目录中的异步爬虫实现
    from .search import TwitterStockScraper
except Exception:
    # 兼容直接运行文件的情形
    from search import TwitterStockScraper  # type: ignore


def _run_async(coro):
    """在尽可能多的环境中安全运行异步协程。

    - 优先使用 asyncio.run（无事件循环时）
    - 若当前已有事件循环未运行，使用 run_until_complete
    - 若事件循环正在运行（如部分 Notebook/Agent 环境），
      则在线程内创建新事件循环以避免冲突
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已运行的事件循环环境中创建新循环并在线程中执行
            import threading

            result_container: Dict[str, Any] = {}

            def _target():
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    result_container["value"] = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()

            th = threading.Thread(target=_target, daemon=True)
            th.start()
            th.join()
            return result_container.get("value")
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # 无事件循环时使用 asyncio.run
        return asyncio.run(coro)


class XSearchArgs(BaseModel):
    """用于 LangChain StructuredTool 的参数模型"""

    stock_symbol: str = Field(..., description="股票代码，如 AAPL/TSLA/GOOGL")
    max_tweets: Optional[int] = Field(
        None, ge=1, le=500, description="最大抓取推文数量；未提供时使用 config.MAX_TWEETS_PER_STOCK"
    )
    headless: Optional[bool] = Field(
        None, description="是否使用无头模式；未提供时使用 config.HEADLESS（首次登录建议 False）"
    )


def _x_search_invoke(stock_symbol: str, max_tweets: Optional[int] = None, headless: Optional[bool] = None) -> str:
    """同步封装：抓取指定股票相关推文并返回 JSON 字符串。

    返回结构：
    {
      "ok": true/false,
      "symbol": "TSLA",
      "count": 20,
      "tweets": [...],      # 当 ok=true 时返回
      "error": "..."        # 当 ok=false 时返回
    }
    """

    async def _worker():
        try:
            # 解析默认参数来自 config
            try:
                try:
                    from .config import Config as Cfg
                except Exception:
                    from config import Config as Cfg
            except Exception:
                Cfg = type("Cfg", (), {})  # type: ignore

            eff_headless = headless if headless is not None else getattr(Cfg, 'HEADLESS', True)
            eff_max_tweets = max_tweets if max_tweets is not None else getattr(Cfg, 'MAX_TWEETS_PER_STOCK', 20)

            async with TwitterStockScraper(headless=eff_headless) as scraper:
                tweets = await scraper.search_stock_tweets(stock_symbol, max_tweets=eff_max_tweets)
                return {
                    "ok": True,
                    "symbol": stock_symbol,
                    "count": len(tweets or []),
                    "tweets": tweets or [],
                }
        except Exception as e:  # pragma: no cover
            return {
                "ok": False,
                "symbol": stock_symbol,
                "count": 0,
                "error": str(e),
            }

    result: Dict[str, Any] = _run_async(_worker())
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:  # pragma: no cover
        # 兜底防止因非序列化对象导致报错
        if result.get("ok") and isinstance(result.get("tweets"), list):
            result = {k: v for k, v in result.items() if k != "tweets"}
        return json.dumps(result, ensure_ascii=False)


def build_x_search_tool(name: Optional[str] = None, description: Optional[str] = None):
    """构建并返回一个 LangChain StructuredTool，用于 X/Twitter 股票舆情检索。

    示例（在 Agent 中使用）：
        tool = build_x_search_tool()
        agent = initialize_agent([tool], llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
    """

    if StructuredTool is None:  # pragma: no cover
        raise ImportError(
            "未检测到 LangChain 的 StructuredTool，请先安装 langchain>=0.1 或 langchain-core。"
        )

    tool_name = name or "x_search_stock_tweets"
    tool_desc = description or (
        "使用 Playwright 登录并检索 X/Twitter 上与指定股票相关的近期推文。"
        "输入: stock_symbol(必填), max_tweets(默认50), headless(默认False)。"
        "并行: 通过 Config.PARALLEL_PAGES 与 Config.MAX_PARALLEL_PAGES 控制并行页面数。"
        "输出: JSON 字符串，包含 tweets 列表与统计信息。首次使用建议 headless=False 完成登录。"
    )

    return StructuredTool.from_function(
        name=tool_name,
        description=tool_desc,
        func=_x_search_invoke,
        args_schema=XSearchArgs,  # type: ignore[arg-type]
        return_direct=False,
    )


__all__ = [
    "XSearchArgs",
    "build_x_search_tool",
]


# —— 一致的工具封装：get_sentiment ——

async def get_sentiment_func(ticker: str, max_tweets: Optional[int] = None, headless: Optional[bool] = None) -> str:
    """获取 X/Twitter 上与股票相关的近期推文样本与互动统计（返回 JSON 字符串）。

    - ticker: 股票代码，如 AAPL、TSLA
    - max_tweets: 最大抓取数量；未提供时使用 config.MAX_TWEETS_PER_STOCK
    - headless: 是否使用无头浏览器；未提供时使用 config.HEADLESS
    """

    # 解析默认参数来自 config
    try:
        try:
            from .config import Config as Cfg
        except Exception:
            from config import Config as Cfg
    except Exception:
        Cfg = type("Cfg", (), {})  # type: ignore

    eff_headless = headless if headless is not None else getattr(Cfg, 'HEADLESS', True)
    eff_max_tweets = max_tweets if max_tweets is not None else getattr(Cfg, 'MAX_TWEETS_PER_STOCK', 20)

    async with TwitterStockScraper(headless=eff_headless) as scraper:
        tweets = await scraper.search_stock_tweets(ticker, max_tweets=eff_max_tweets)
        result: Dict[str, Any] = {
            "ticker": ticker,
            "count": len(tweets or []),
            "tweets": tweets or [],
        }

    # 可选输出到文件（受 config 控制）
    try:
        output_formats = getattr(Cfg, 'OUTPUT_FORMAT', []) or []
        if 'json' in [str(x).lower() for x in output_formats]:
            out_dir = Path(getattr(Cfg, 'OUTPUT_DIR', 'output'))
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            out_path = out_dir / f"{ticker}_tweets_{ts}.json"
            with out_path.open('w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return json.dumps(result, ensure_ascii=False)


# 与 fundamentals 的模式保持一致：同时提供 func 与 coroutine
get_sentiment = StructuredTool.from_function(
    func=get_sentiment_func,
    coroutine=get_sentiment_func,
    name="get_sentiment",
    description=(
        "Get recent tweet samples and basic interaction stats from X/Twitter for a given stock ticker. "
        "Returns a JSON string. Useful for gauging short-term market sentiment signals."
    ),
)


