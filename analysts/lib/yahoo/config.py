# 核心配置
CONFIG = {
    "timeout": 30,
    "max_retries": 3,
    "retry_delay": 1.0,
    "default_period": "1mo",
    "default_interval": "1d",
    "max_news": 10,
    "output_dir": "output",
}

# 主要市场指数
INDICES = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ",
    "^VIX": "VIX",
    "^RUT": "Russell 2000",
}

# 支持的参数
PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
INTERVALS = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"]
