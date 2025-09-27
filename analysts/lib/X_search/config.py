import os
from datetime import datetime, timedelta


class Config:
    """
    集中配置管理
    """
    # 浏览器设置
    HEADLESS = True
    DELAY_RANGE = (1, 3)
    DISABLE_MEDIA = True
    
    # 爬取设置
    MAX_TWEETS_PER_STOCK = 100
    MAX_SCROLL_ATTEMPTS = 50
    PARALLEL_PAGES = 6
    
    # 文件路径 - 专业的数据文件管理
    _MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = os.path.join(_MODULE_DIR, 'cookies')
    
    # 确保数据目录存在
    os.makedirs(_DATA_DIR, exist_ok=True)
    
    COOKIES_JSON_PATH = os.path.join(_DATA_DIR, "cookies.json")
    STORAGE_STATE_PATH = os.path.join(_DATA_DIR, 'state.json')
    
    # 搜索设置
    FINANCE_KEYWORDS = ['stock', 'shares', '财报', '股价', 'trading', 'market']
    
    # 时间窗口
    _today = datetime.utcnow().date()
    SINCE = (_today - timedelta(days=5)).strftime('%Y-%m-%d')
    UNTIL = _today.strftime('%Y-%m-%d')
    
    # 质量过滤阈值
    MIN_LIKES = 0
    MIN_RETWEETS = 0
    MIN_REPLIES = 0
    MIN_TEXT_LEN = 20
    
    # 股票搜索关键词映射
    SEARCH_KEYWORDS = {
        'AAPL': ['$AAPL', 'Apple', '苹果'],
        'TSLA': ['$TSLA', 'Tesla', '特斯拉'],
        'GOOGL': ['$GOOGL', 'Google', '谷歌'],
        'MSFT': ['$MSFT', 'Microsoft', '微软'],
        'AMZN': ['$AMZN', 'Amazon', '亚马逊'],
        'NVDA': ['$NVDA', 'Nvidia', '英伟达'],
        'META': ['$META', 'Meta', 'Facebook', '脸书'],
    }
    
    @classmethod
    def get_search_keywords(cls, ticker: str) -> list:
        """获取股票搜索关键词="""
        return cls.SEARCH_KEYWORDS.get(ticker, [f"${ticker}"])
    
    @classmethod
    def validate(cls):
        """配置验证"""
        assert cls.MAX_TWEETS_PER_STOCK > 0, "MAX_TWEETS_PER_STOCK must be positive"
        assert cls.PARALLEL_PAGES > 0, "PARALLEL_PAGES must be positive"
        assert os.path.exists(cls._DATA_DIR), "Data directory must exist"
        return True


# 运行时验证配置
Config.validate()
