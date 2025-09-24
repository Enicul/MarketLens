"""
Yahoo Finance 工具配置文件

包含工具的默认配置和设置
"""

# 默认配置
DEFAULT_CONFIG = {
    # 请求设置
    "timeout": 30,  # 请求超时时间（秒）
    "max_retries": 3,  # 最大重试次数
    "retry_delay": 1.0,  # 重试延迟（秒）
    
    # 数据设置
    "default_period": "1mo",  # 默认历史数据周期
    "default_interval": "1d",  # 默认数据间隔
    "max_news": 10,  # 默认最大新闻数量
    "max_search_results": 10,  # 默认最大搜索结果数量
    
    # 技术指标设置
    "rsi_period": 14,  # RSI计算周期
    "macd_fast": 12,  # MACD快线周期
    "macd_slow": 26,  # MACD慢线周期
    "macd_signal": 9,  # MACD信号线周期
    "bb_period": 20,  # 布林带周期
    "bb_std": 2,  # 布林带标准差倍数
    
    # 移动平均线设置
    "ma_periods": [5, 10, 20, 50],  # 移动平均线周期
    
    # 日志设置
    "log_level": "INFO",  # 日志级别
    "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    
    # 缓存设置
    "enable_cache": False,  # 是否启用缓存
    "cache_ttl": 300,  # 缓存生存时间（秒）
    
    # 请求限制
    "request_delay": 0.1,  # 请求间延迟（秒）
    "max_concurrent_requests": 5,  # 最大并发请求数
}

# 支持的股票交易所
SUPPORTED_EXCHANGES = [
    "NASDAQ",
    "NYSE", 
    "AMEX",
    "TSX",  # 多伦多
    "LSE",  # 伦敦
    "TSE",  # 东京
    "HKEX", # 香港
    "SSE",  # 上海
    "SZSE", # 深圳
]

# 支持的时间周期
SUPPORTED_PERIODS = [
    "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
]

# 支持的数据间隔
SUPPORTED_INTERVALS = [
    "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"
]

# 主要市场指数
MAJOR_INDICES = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones Industrial Average",
    "^IXIC": "NASDAQ Composite",
    "^VIX": "CBOE Volatility Index",
    "^RUT": "Russell 2000",
    "^FTSE": "FTSE 100",
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng Index",
    "^AXJO": "S&P/ASX 200",
    "^GDAXI": "DAX",
    "^FCHI": "CAC 40",
}

# 技术指标配置
TECHNICAL_INDICATORS = {
    "rsi": {
        "name": "Relative Strength Index",
        "default_period": 14,
        "overbought": 70,
        "oversold": 30
    },
    "macd": {
        "name": "Moving Average Convergence Divergence",
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
    },
    "bollinger_bands": {
        "name": "Bollinger Bands",
        "period": 20,
        "std_dev": 2
    },
    "moving_averages": {
        "name": "Moving Averages",
        "periods": [5, 10, 20, 50, 200]
    }
}

# 错误消息
ERROR_MESSAGES = {
    "INVALID_SYMBOL": "无效的股票代码",
    "NETWORK_ERROR": "网络连接错误",
    "TIMEOUT_ERROR": "请求超时",
    "DATA_NOT_FOUND": "未找到数据",
    "RATE_LIMIT": "请求频率过高",
    "UNKNOWN_ERROR": "未知错误"
}

# 成功消息
SUCCESS_MESSAGES = {
    "DATA_RETRIEVED": "数据获取成功",
    "CACHE_HIT": "缓存命中",
    "RETRY_SUCCESS": "重试成功"
}

def get_config(key: str = None, default=None):
    """
    获取配置值
    
    Args:
        key: 配置键，如果为None则返回所有配置
        default: 默认值
        
    Returns:
        配置值或所有配置字典
    """
    if key is None:
        return DEFAULT_CONFIG.copy()
    
    return DEFAULT_CONFIG.get(key, default)

def update_config(**kwargs):
    """
    更新配置
    
    Args:
        **kwargs: 要更新的配置项
    """
    DEFAULT_CONFIG.update(kwargs)

def validate_config():
    """
    验证配置的有效性
    
    Returns:
        bool: 配置是否有效
    """
    try:
        # 验证超时时间
        if DEFAULT_CONFIG["timeout"] <= 0:
            return False
        
        # 验证重试次数
        if DEFAULT_CONFIG["max_retries"] < 0:
            return False
        
        # 验证延迟时间
        if DEFAULT_CONFIG["retry_delay"] < 0:
            return False
        
        # 验证周期
        if DEFAULT_CONFIG["default_period"] not in SUPPORTED_PERIODS:
            return False
        
        # 验证间隔
        if DEFAULT_CONFIG["default_interval"] not in SUPPORTED_INTERVALS:
            return False
        
        return True
        
    except Exception:
        return False

# 验证配置
if not validate_config():
    raise ValueError("配置验证失败，请检查配置项的有效性")
