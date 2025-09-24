# 配置文件
from datetime import datetime, timedelta

class Config:
    # 浏览器设置
    HEADLESS = False  # 是否无头模式
    DELAY_RANGE = (1, 3)  # 请求间隔时间范围（秒）
    
    # 爬取设置
    MAX_TWEETS_PER_STOCK = 10  # 每个股票最大爬取推文数
    MAX_SCROLL_ATTEMPTS = 50   # 最大滚动次数
    
    # 输出设置
    OUTPUT_FORMAT = ['json', 'csv']  # 输出格式

    OUTPUT_DIR = 'output'  # 输出目录
    
    COOKIES_JSON_PATH = "X_cookies.json"
    # 登录态持久化：Playwright storage_state 文件路径
    STORAGE_STATE_PATH = './auth_state.json'

    # 搜索Tab：'top'（默认）或 'latest'
    SEARCH_TAB = 'top'

    # 基础搜索设置（简洁不复杂）
    LANG = None  # 可设为 'en' 或 'zh'，None 表示不限定
    """FINANCE_KEYWORDS = [
        'stock', 'shares', 'earnings', 'EPS', 'revenue', 'guidance',
        'price target', 'forecast', 'upgrade', 'downgrade',
        '财报', '股价', '指引', '目标价', '回购'
    ]"""
    FINANCE_KEYWORDS = [
        'stock', 'shares',
        '财报', '股价', 
    ]
    # 日期窗口（可选，格式 YYYY-MM-DD）
    # 默认：今天(UTC)起往前5天至今天
    _today = datetime.utcnow().date()
    SINCE = (_today - timedelta(days=5)).strftime('%Y-%m-%d')
    UNTIL = _today.strftime('%Y-%m-%d')

    # 简单质量过滤阈值（抓取后筛选使用，可按需调优）
    MIN_LIKES = 0
    MIN_RETWEETS = 0
    MIN_REPLIES =0
    MIN_TEXT_LEN = 20

    # 是否排除转推与回复（更聚焦原创讨论）
    # EXCLUDE_RETWEETS = True
    # EXCLUDE_REPLIES = False

    # 仅抓取新闻类帖子（包含外链，且可选限定新闻域名）
    NEWS_ONLY = False
    """NEWS_DOMAINS = [
        'bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 'cnbc.com',
        'seekingalpha.com', 'marketwatch.com', 'yahoo.com', 'fool.com',
        'investopedia.com', 'thestreet.com', 'investors.com'
    ]"""

    # 评论抓取设置(有bug）
    FETCH_REPLIES =  False         # 是否抓取评论区内容
    MAX_REPLIES_PER_TWEET = 10     # 每条主贴最多抓取多少条评论
    REPLIES_MIN_TEXT_LEN = 5       # 评论最小文本长度

    PARALLEL_PAGES = 2   # 多页面并行抓取

    # 股票列表
    STOCK_SYMBOLS = [
        'AAPL',   # 苹果
        'TSLA',   # 特斯拉
        'GOOGL',  # 谷歌
        'MSFT',   # 微软
        'AMZN',   # 亚马逊
        'NVDA',   # 英伟达
        'META',   # Meta
        'NFLX',   # 奈飞
    ]
    
    # 搜索关键词（可选）
    SEARCH_KEYWORDS = {
        'AAPL': ['$AAPL', 'Apple', '苹果'],
        'TSLA': ['$TSLA', 'Tesla', '特斯拉'],
        'GOOGL': ['$GOOGL', 'Google', '谷歌'],
        'MSFT': ['$MSFT', 'Microsoft', '微软'],
        'AMZN': ['$AMZN', 'Amazon', '亚马逊'],
    }