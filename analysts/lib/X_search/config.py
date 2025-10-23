import os
from datetime import datetime, timedelta


class Config:
    """
    Centralized configuration for the X/Twitter sentiment pipeline.
    """
    # Browser configuration
    HEADLESS = True  # headless mode recommended for stability
    DELAY_RANGE = (1, 3)
    DISABLE_MEDIA = True
    
    # Scraper settings
    MAX_TWEETS_PER_STOCK = 80
    MAX_SCROLL_ATTEMPTS = 50
    PARALLEL_PAGES = 2  # limit concurrency to improve stability
    
    # Data directories
    _MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = os.path.join(_MODULE_DIR, 'cookies')
    
    # Ensure data directory exists
    os.makedirs(_DATA_DIR, exist_ok=True)
    
    COOKIES_JSON_PATH = os.path.join(_DATA_DIR, "cookies.json")
    STORAGE_STATE_PATH = os.path.join(_DATA_DIR, 'state.json')
    
    # Search keyword configuration
    FINANCE_KEYWORDS = ['stock', 'shares', 'earnings', 'share price', 'trading', 'market']
    
    # Time window
    _today = datetime.utcnow().date()
    SINCE = (_today - timedelta(days=5)).strftime('%Y-%m-%d')
    UNTIL = _today.strftime('%Y-%m-%d')
    
    # Quality thresholds
    MIN_LIKES = 0
    MIN_RETWEETS = 0
    MIN_REPLIES = 0
    MIN_TEXT_LEN = 20
    
    # Stock-specific keyword mapping
    SEARCH_KEYWORDS = {
        'AAPL': ['$AAPL', 'Apple'],
        'TSLA': ['$TSLA', 'Tesla'],
        'GOOGL': ['$GOOGL', 'Google'],
        'MSFT': ['$MSFT', 'Microsoft'],
        'AMZN': ['$AMZN', 'Amazon'],
        'NVDA': ['$NVDA', 'Nvidia'],
        'META': ['$META', 'Meta', 'Facebook'],
    }
    
    @classmethod
    def get_search_keywords(cls, ticker: str) -> list:
        """Return keyword list for a ticker."""
        return cls.SEARCH_KEYWORDS.get(ticker, [f"${ticker}"])
    
    @classmethod
    def validate(cls):
        """Validate configuration invariants."""
        assert cls.MAX_TWEETS_PER_STOCK > 0, "MAX_TWEETS_PER_STOCK must be positive"
        assert cls.PARALLEL_PAGES > 0, "PARALLEL_PAGES must be positive"
        assert os.path.exists(cls._DATA_DIR), "Data directory must exist"
        return True

# Runtime validation hook
Config.validate()
