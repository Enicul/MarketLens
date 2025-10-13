import traceback
from datetime import datetime, timezone
from typing import Dict, Any
from langchain.tools import StructuredTool
from .search import TwitterScraper, ScraperConfig
from .config import Config  
from .sentiment import AdvancedSentimentAnalyzer


async def get_sentiment_func(ticker: str) -> Dict[str, Any]:
    """
    获取股票在 Twitter/X 平台上的社交媒体情绪数据
    
    Args:
        ticker: 股票代码
        
    Returns:
        包含情绪分析结果的字典
    """
    print(f"\n[SENTIMENT] 🐦 Starting Twitter sentiment analysis for {ticker}")
    print("  " + "-" * 40)
    # 爬虫配置 - 看好了，这才叫简洁的配置使用
    config = ScraperConfig(
        headless=Config.HEADLESS,
        storage_state_path=Config.STORAGE_STATE_PATH,
        max_tweets=Config.MAX_TWEETS_PER_STOCK,
        parallel_pages=Config.PARALLEL_PAGES,
        min_likes=Config.MIN_LIKES,
        min_retweets=Config.MIN_RETWEETS,
        min_replies=Config.MIN_REPLIES,
        min_text_length=Config.MIN_TEXT_LEN,
        finance_keywords=Config.FINANCE_KEYWORDS,
        cookies_path=Config.COOKIES_JSON_PATH,
        exclude_retweets=False,
        exclude_replies=False,
    )
    
    try:
        async with TwitterScraper(config) as scraper:
            # 数据获取层
            print(f"[SENTIMENT] 📥 Scraping tweets for {ticker}")
            tweets = await scraper.scrape_stock_tweets(ticker)
            print(f"[SENTIMENT] 📊 Found {len(tweets)} tweets")
            
            # 分析层
            print(f"[SENTIMENT] 🔍 Analyzing sentiment...")
            analyzer = AdvancedSentimentAnalyzer()
            metrics, top_tweets = analyzer.analyze(tweets, top_k=Config.TOP_TWEETS_TO_SAVE)
            
            # 数据组装层 - 专业的数据结构
            result = {
                "ticker": ticker,
                "channel": "sentiment",
                "overall_sentiment": metrics.overall_sentiment,
                "sentiment_score": metrics.sentiment_score,
                "sentiment_breakdown": metrics.sentiment_breakdown,
                "metrics": {
                    "total_tweets": len(tweets),
                    "total_influence": sum(t.engagement_score for t in tweets),
                    "influence_concentration": metrics.influence_concentration,
                    "sentiment_volatility": metrics.sentiment_volatility,
                    "quality_score": metrics.quality_score
                },
                "top_tweets": top_tweets,
                "analysis_metadata": {
                    "algorithm_version": "3.0-professional",  # 不是modular，是professional
                    "confidence_level": metrics.confidence_level,
                    "search_keywords": Config.get_search_keywords(ticker),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "processing_note": "Professional sentiment analysis with integrated architecture"
                }
            }
            print(f"[SENTIMENT] ✅ Complete for {ticker} - {metrics.overall_sentiment} ({metrics.sentiment_score:.3f})")
            print("  " + "=" * 40)
            return result
            
    except Exception as e:
        # 错误处理 - 专业的错误响应
        print(f"[SENTIMENT] ❌ Error for {ticker}: {str(e)[:50]}...")
        return _build_error_response(ticker, e)


def _build_error_response(ticker: str, error: Exception) -> Dict[str, Any]:
    """构建错误响应"""
    return {
        "ticker": ticker,
        "channel": "sentiment",
        "error": {
            "message": str(error),
            "type": type(error).__name__,
            "traceback": traceback.format_exc() if not Config.HEADLESS else "Enable debug mode for traceback"
        },
        "overall_sentiment": "error",
        "sentiment_score": 0.0,
        "sentiment_breakdown": {"bullish": 0, "bearish": 0, "neutral": 1.0},
        "metrics": {
            "total_tweets": 0,
            "total_influence": 0,
            "influence_concentration": 0,
            "sentiment_volatility": 0,
            "quality_score": 0
        },
        "top_tweets": [],
        "analysis_metadata": {
            "algorithm_version": "3.0-professional",
            "confidence_level": 0,
            "error_occurred": True,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    }


# LangChain 工具
get_sentiment = StructuredTool.from_function(
    func=get_sentiment_func,
    coroutine=get_sentiment_func,
    name="get_sentiment",
    description=(
        "获取指定股票在 Twitter/X 平台上的社交媒体情绪分析。"
        "使用高级算法分析推文内容、用户影响力和市场情绪。"
        "包含五级情绪分类、影响力加权和多维度质量指标。"
    ),
)
