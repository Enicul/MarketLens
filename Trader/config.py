"""
Trader Agent Configuration
管理所有Trader相关的配置参数
"""

import os

# OpenAI API Configuration
OPENAI_API_KEY = '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'
OPENAI_MODEL = 'gpt-4o-mini'
OPENAI_TEMPERATURE = 0

# Trader Agent Settings
TRADER_VERBOSE = True
KRONOS_VERBOSE = False

# File Paths
RESEARCHER_FILE = 'researcher.json'
KRONOS_DATA_PATH = 'Kronos/examples/data/'

# Trading Parameters
DEFAULT_LOOKBACK = 400
DEFAULT_PRED_LEN = 120
MAX_POSITION_SIZE = 0.25
MIN_POSITION_SIZE = 0.05

# Risk Management
DEFAULT_STOP_LOSS = 0.08
DEFAULT_TAKE_PROFIT = 0.12
MAX_DRAWDOWN_MULTIPLIER = 1.5

# Decision Thresholds
BUY_THRESHOLD = 0.3
SELL_THRESHOLD = -0.3
HIGH_CONFIDENCE_THRESHOLD = 0.7
KRONOS_USE_THRESHOLD = 2  # Number of factors needed to use Kronos

def setup_environment():
    """设置环境变量"""
    os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
    return True

def get_openai_config():
    """获取OpenAI配置"""
    return {
        'api_key': OPENAI_API_KEY,
        'model': OPENAI_MODEL,
        'temperature': OPENAI_TEMPERATURE
    }

def get_trading_config():
    """获取交易配置"""
    return {
        'lookback': DEFAULT_LOOKBACK,
        'pred_len': DEFAULT_PRED_LEN,
        'max_position_size': MAX_POSITION_SIZE,
        'min_position_size': MIN_POSITION_SIZE,
        'stop_loss': DEFAULT_STOP_LOSS,
        'take_profit': DEFAULT_TAKE_PROFIT,
        'buy_threshold': BUY_THRESHOLD,
        'sell_threshold': SELL_THRESHOLD
    }

def get_file_paths():
    """获取文件路径配置"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    return {
        'researcher_file': os.path.join(project_root, RESEARCHER_FILE),
        'kronos_data_path': os.path.join(current_dir, KRONOS_DATA_PATH),
        'current_dir': current_dir,
        'project_root': project_root
    }

# 自动设置环境变量
setup_environment()

if __name__ == "__main__":
    print("🔧 Trader Agent 配置信息:")
    print(f"OpenAI API Key: {OPENAI_API_KEY[:20]}...")
    print(f"Model: {OPENAI_MODEL}")
    print(f"Temperature: {OPENAI_TEMPERATURE}")
    print(f"Researcher File: {RESEARCHER_FILE}")
    print(f"Kronos Data Path: {KRONOS_DATA_PATH}")
    print("✅ 配置加载完成")
