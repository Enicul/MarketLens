# 配置文件
from datetime import datetime, timedelta

class Config:
    # 浏览器设置
    HEADLESS = False  # 是否无头模式
    DELAY_RANGE = (1, 3)  # 请求间隔时间范围（秒）
    DISABLE_MEDIA = True  # 禁止图片和视频加载以提高速度
    
    # 爬取设置
    MAX_TWEETS_PER_STOCK = 30  # 每个股票最大爬取推文数
    MAX_SCROLL_ATTEMPTS = 50   # 最大滚动次数
    PARALLEL_PAGES = 6  # 多页面并行抓取
    
    # 文件路径
    COOKIES_JSON_PATH = "X_cookies.json"
    STORAGE_STATE_PATH = './state.json'
    
    # 搜索设置
    FINANCE_KEYWORDS = ['stock', 'shares', '财报', '股价']
    
    # 时间窗口（今天起往前5天）
    _today = datetime.utcnow().date()
    SINCE = (_today - timedelta(days=5)).strftime('%Y-%m-%d')
    UNTIL = _today.strftime('%Y-%m-%d')
    
    # 质量过滤阈值
    MIN_LIKES = 0
    MIN_RETWEETS = 0
    MIN_REPLIES = 0
    MIN_TEXT_LEN = 20
    
    # 搜索关键词
    SEARCH_KEYWORDS = {
        'AAPL': ['$AAPL', 'Apple', '苹果'],
        'TSLA': ['$TSLA', 'Tesla', '特斯拉'],
        'GOOGL': ['$GOOGL', 'Google', '谷歌'],
        'MSFT': ['$MSFT', 'Microsoft', '微软'],
        'AMZN': ['$AMZN', 'Amazon', '亚马逊'],
    }