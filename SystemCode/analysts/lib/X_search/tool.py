import asyncio
import traceback
from datetime import datetime, timezone
from typing import Dict, Any
from langchain.tools import StructuredTool
from .search import TwitterScraper, ScraperConfig
from .config import Config  
from .sentiment import AdvancedSentimentAnalyzer
import logging

logger = logging.getLogger(__name__)

async def get_sentiment_func(ticker: str) -> Dict[str, Any]:
    """
    Gather Twitter/X social sentiment for the requested equity.
    
    Args:
        ticker: Stock ticker symbol.
        
    Returns:
        A dictionary containing sentiment analysis results.
    """
    logger.info(f"\n[SENTIMENT] 🐦 Starting Twitter sentiment analysis for {ticker}")
    # Scraper configuration
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
        # Retry with lightweight backoff
        max_retries = 2
        tweets = []
        
        for attempt in range(max_retries):
            try:
                async with TwitterScraper(config) as scraper:
                    # Data acquisition layer
                    logger.info(f"[SENTIMENT] 📥 Collecting tweets for {ticker} (attempt {attempt + 1}/{max_retries})")
                    tweets = await scraper.scrape_stock_tweets(ticker)
                    logger.info(f"[SENTIMENT] 📊 Tweets gathered: {len(tweets)}")
                    break  # successful run
            except Exception as retry_error:
                logger.warning(f"[SENTIMENT] ⚠️ Attempt {attempt + 1} failed: {str(retry_error)[:50]}...")
                if attempt == max_retries - 1:  # final attempt
                    raise retry_error
                await asyncio.sleep(2)  # wait before retry
        
        # Analysis layer
        logger.info(f"[SENTIMENT] 🔍 Running sentiment analytics...")
        analyzer = AdvancedSentimentAnalyzer()
        metrics, top_tweets = analyzer.analyze(tweets)
        
        # Assembly layer
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
                "algorithm_version": "3.0-professional",
                "confidence_level": metrics.confidence_level,
                "search_keywords": Config.get_search_keywords(ticker),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "processing_note": "Professional sentiment analysis with integrated architecture"
            }
        }
        logger.info(f"[SENTIMENT] ✅ Sentiment analysis complete: {ticker} — {metrics.overall_sentiment} (score {metrics.sentiment_score:.3f})")
        return result
            
    except Exception as e:
        # Structured error handling
        error_msg = str(e)
        logger.error(f"[SENTIMENT] ❌ Error for {ticker}: {error_msg[:50]}...")
        
        # Provide actionable tips for browser issues
        if "Executable doesn't exist" in error_msg or "chromium" in error_msg.lower():
            logger.warning(f"[SENTIMENT] 💡 Tip: run 'playwright install chromium' to install the browser dependency")
        
        return _build_error_response(ticker, e)


def _build_error_response(ticker: str, error: Exception) -> Dict[str, Any]:
    """Build a structured error response payload."""
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


# LangChain tool wrapper
get_sentiment = StructuredTool.from_function(
    func=get_sentiment_func,
    coroutine=get_sentiment_func,
    name="get_sentiment",
    description=(
        "Retrieve Twitter/X social sentiment for a given stock ticker. "
        "Leverages an advanced analyzer to score tweet content, user influence, and market mood. "
        "Includes multi-level sentiment classification, influence weighting, and quality metrics."
    ),
)
