import json
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path

# 相对导入本目录中的异步爬虫实现（兼容直接运行）
try:
    from .search import TwitterScraper
except Exception:
    from search import TwitterScraper  # type: ignore


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

    # 创建配置对象，使用从config.py读取的值
    from .search import ScraperConfig
    config = ScraperConfig(
        headless=eff_headless,
        max_tweets=eff_max_tweets,
        parallel_pages=getattr(Cfg, 'PARALLEL_PAGES', 4),
        max_scroll_attempts=getattr(Cfg, 'MAX_SCROLL_ATTEMPTS', 20),
        min_likes=getattr(Cfg, 'MIN_LIKES', 0),
        min_retweets=getattr(Cfg, 'MIN_RETWEETS', 0),
        min_replies=getattr(Cfg, 'MIN_REPLIES', 0),
        min_text_length=getattr(Cfg, 'MIN_TEXT_LEN', 10),
        finance_keywords=getattr(Cfg, 'FINANCE_KEYWORDS', ["stock", "trading", "bullish", "bearish", "buy", "sell"]),
        storage_state_path=getattr(Cfg, 'STORAGE_STATE_PATH', "./state.json"),
        cookies_path=getattr(Cfg, 'COOKIES_JSON_PATH', "X_cookies.json"),
    )

    async with TwitterScraper(config) as scraper:
        tweets = await scraper.scrape_stock_tweets(ticker)
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


__all__ = ["get_sentiment_func"]
