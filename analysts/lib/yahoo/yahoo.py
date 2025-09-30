import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
import time
from dataclasses import dataclass, asdict, field
from functools import wraps

logger = logging.getLogger(__name__)

# 技术指标自适应配置
INDICATOR_CONFIG = {
    '1m': {'ma': [5, 10, 20, 50], 'rsi': 14, 'macd': (12, 26, 9), 'bb': 20, 'stoch': (14, 3), 'atr': 14},
    '5m': {'ma': [5, 10, 20, 50], 'rsi': 14, 'macd': (12, 26, 9), 'bb': 20, 'stoch': (14, 3), 'atr': 14},
    '1h': {'ma': [5, 10, 20, 50], 'rsi': 14, 'macd': (12, 26, 9), 'bb': 20, 'stoch': (14, 3), 'atr': 14},
    '1d': {'ma': [5, 10, 20, 50], 'rsi': 14, 'macd': (12, 26, 9), 'bb': 20, 'stoch': (14, 3), 'atr': 14},
    '1wk': {'ma': [3, 5, 10, 20], 'rsi': 7, 'macd': (6, 13, 5), 'bb': 10, 'stoch': (7, 2), 'atr': 7},
    '1mo': {'ma': [2, 3, 5, 10], 'rsi': 5, 'macd': (3, 6, 2), 'bb': 5, 'stoch': (5, 2), 'atr': 5},
}

def retry(max_retries=3, delay=1.0):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator

@dataclass
class StockData:
    ticker: str
    current_price: float
    change: float
    change_percent: float
    volume: int
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    beta: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class HistoricalData:
    ticker: str
    data: pd.DataFrame
    period: str
    interval: str
    start_date: str
    end_date: str
    data_points: int

class YahooFinanceTool:
    """简化版Yahoo Finance工具"""
    
    def __init__(self, timeout: int = 30, output_dir: str = "output"):
        self.timeout = timeout
        self.output_dir = output_dir
        # os.makedirs(output_dir, exist_ok=True)
    
    def _get_ticker(self, symbol: str) -> yf.Ticker:
        ticker = yf.Ticker(symbol)
        if not ticker.info:
            raise ValueError(f"无效股票代码: {symbol}")
        return ticker
    
    @retry()
    def get_stock_info(self, symbol: str) -> StockData:
        ticker = self._get_ticker(symbol)
        info = ticker.info
        
        price = info.get('currentPrice', info.get('regularMarketPrice', 0))
        prev_close = info.get('previousClose', price)
        change = price - prev_close
        
        return StockData(
            ticker=symbol.upper(),
            current_price=round(price, 2),
            change=round(change, 2),
            change_percent=round(change / prev_close * 100 if prev_close else 0, 2),
            volume=info.get('volume', 0),
            market_cap=info.get('marketCap'),
            pe_ratio=info.get('trailingPE'),
            pb_ratio=info.get('priceToBook'),
            dividend_yield=info.get('dividendYield'),
            beta=info.get('beta'),
            high_52w=info.get('fiftyTwoWeekHigh'),
            low_52w=info.get('fiftyTwoWeekLow')
        )
    
    @retry()
    def get_historical_data(self, symbol: str, period: str = "1mo", interval: str = "1d") -> HistoricalData:
        ticker = self._get_ticker(symbol)
        hist = ticker.history(period=period, interval=interval, timeout=self.timeout)
        
        if hist.empty:
            raise ValueError(f"无历史数据: {symbol}")
        
        hist = self._add_indicators(hist.dropna(), interval)
        
        return HistoricalData(
            ticker=symbol.upper(),
            data=hist,
            period=period,
            interval=interval,
            start_date=hist.index[0].strftime('%Y-%m-%d'),
            end_date=hist.index[-1].strftime('%Y-%m-%d'),
            data_points=len(hist)
        )
    
    def _add_indicators(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """添加技术指标"""
        close = df['Close']
        config = INDICATOR_CONFIG.get(interval, INDICATOR_CONFIG['1d'])
        
        # 移动平均线
        for window in config['ma']:
            if len(df) >= window:
                df[f'MA_{window}'] = close.rolling(window).mean()
        
        # RSI
        if len(df) >= config['rsi']:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(config['rsi']).mean()
            loss = -delta.where(delta < 0, 0).rolling(config['rsi']).mean()
            df['RSI'] = 100 - (100 / (1 + gain / loss))
        
        # MACD
        if len(df) >= config['macd'][1]:
            ema_fast = close.ewm(span=config['macd'][0]).mean()
            ema_slow = close.ewm(span=config['macd'][1]).mean()
            df['MACD'] = ema_fast - ema_slow
            df['MACD_Signal'] = df['MACD'].ewm(span=config['macd'][2]).mean()
            df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
        
        # 布林带
        if len(df) >= config['bb']:
            sma = close.rolling(config['bb']).mean()
            std = close.rolling(config['bb']).std()
            df['BB_Upper'] = sma + 2 * std
            df['BB_Middle'] = sma
            df['BB_Lower'] = sma - 2 * std
        
        # 成交量均线
        for window in [10, 20]:
            if len(df) >= window:
                df[f'Volume_MA_{window}'] = df['Volume'].rolling(window).mean()
        
        # 随机指标
        if len(df) >= config['stoch'][0]:
            low_min = df['Low'].rolling(config['stoch'][0]).min()
            high_max = df['High'].rolling(config['stoch'][0]).max()
            df['Stoch_K'] = 100 * (close - low_min) / (high_max - low_min)
            df['Stoch_D'] = df['Stoch_K'].rolling(config['stoch'][1]).mean()
        
        # ATR
        if len(df) >= config['atr']:
            high_low = df['High'] - df['Low']
            high_close = (df['High'] - close.shift()).abs()
            low_close = (df['Low'] - close.shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['ATR'] = tr.rolling(config['atr']).mean()
        
        return df
    
    def get_multiple_stocks(self, symbols: List[str]) -> Dict[str, StockData]:
        """批量获取股票信息"""
        return {s: self.get_stock_info(s) for s in symbols if self._safe_get(s)}
    
    def _safe_get(self, symbol: str) -> Optional[StockData]:
        try:
            return self.get_stock_info(symbol)
        except:
            return None
    
    def get_market_summary(self) -> Dict[str, Any]:
        """获取市场概况"""
        indices = {'^GSPC': 'S&P 500', '^DJI': 'Dow Jones', '^IXIC': 'NASDAQ', '^VIX': 'VIX'}
        summary = {}
        
        for symbol, name in indices.items():
            if data := self._safe_get(symbol):
                summary[name] = {
                    'price': data.current_price,
                    'change': data.change,
                    'change_percent': data.change_percent
                }
        
        return summary
    
    def export_kline_to_csv(self, symbol: str, period: str = "1mo", interval: str = "1d") -> str:
        """导出K线数据到CSV"""
        hist_data = self.get_historical_data(symbol, period, interval)
        df = hist_data.data.reset_index()
        
        # 列名映射
        rename_map = {
            'Date': '日期', 'Open': '开盘价', 'High': '最高价', 
            'Low': '最低价', 'Close': '收盘价', 'Volume': '成交量',
            'RSI': 'RSI指标', 'MACD': 'MACD', 'MACD_Signal': 'MACD信号线',
            'MACD_Histogram': 'MACD柱状图', 'BB_Upper': '布林带上轨',
            'BB_Middle': '布林带中轨', 'BB_Lower': '布林带下轨',
            'Stoch_K': '随机指标K', 'Stoch_D': '随机指标D', 'ATR': '平均真实波幅'
        }
        
        # 动态添加MA和Volume MA列名
        time_unit = {'1d': '日', '1h': '小时', '5m': '个5分钟', '1wk': '周', '1mo': '月'}.get(interval, '期')
        for col in df.columns:
            if col.startswith('MA_'):
                rename_map[col] = f"{col.split('_')[1]}{time_unit}均线"
            elif col.startswith('Volume_MA_'):
                rename_map[col] = f"成交量{col.split('_')[2]}{time_unit}均线"
        
        df = df.rename(columns=rename_map)
        if '日期' in df.columns:
            df['日期'] = df['日期'].dt.strftime('%Y-%m-%d')
        
        filename = f"{symbol}_{period}_{interval}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        logger.info(f"K线数据已导出到: {filepath} (共{len(df)}条)")
        return filepath
    
    def export_analysis_to_json(self, symbol: str, period: str = "1mo", interval: str = "1d") -> str:
        """导出分析数据到JSON"""
        hist_data = self.get_historical_data(symbol, period, interval)
        stock_info = self.get_stock_info(symbol)
        df = hist_data.data
        
        # 构建分析数据
        analysis = {
            "stock_basic_info": asdict(stock_info),
            "technical_indicators": self._extract_indicators(df),
            "price_analysis": self._analyze_price(df),
            "data_summary": {
                "historical_data_points": hist_data.data_points,
                "data_period": hist_data.period,
                "start_date": hist_data.start_date,
                "end_date": hist_data.end_date,
                "last_updated": datetime.now().isoformat()
            }
        }
        
        filename = f"{symbol}_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"分析数据已导出到: {filepath}")
        return filepath
    
    def _extract_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取最新技术指标"""
        if df.empty:
            return {}
        
        latest = df.iloc[-1]
        close = latest['Close']
        volume = latest['Volume']
        
        indicators = {
            "moving_averages": {},
            "oscillators": {},
            "bollinger_bands": {},
            "volume_indicators": {},
            "volatility_indicators": {}
        }
        
        # 移动平均线
        for col in ['MA_20', 'MA_50']:
            if col in df.columns and not pd.isna(latest[col]):
                indicators["moving_averages"][col.lower()] = float(latest[col])
                indicators["moving_averages"][f"price_vs_{col.lower()}"] = float(close / latest[col] * 100)
        
        # 震荡指标
        for col, key in [('RSI', 'rsi'), ('Stoch_K', 'stochastic_k'), 
                         ('Stoch_D', 'stochastic_d'), ('MACD', 'macd')]:
            if col in df.columns and not pd.isna(latest[col]):
                indicators["oscillators"][key] = float(latest[col])
        
        # 布林带
        if 'BB_Upper' in df.columns:
            indicators["bollinger_bands"]["upper_band"] = float(latest['BB_Upper'])
            indicators["bollinger_bands"]["lower_band"] = float(latest['BB_Lower'])
            indicators["bollinger_bands"]["price_vs_upper_band"] = float(close / latest['BB_Upper'] * 100)
        
        # 成交量
        if 'Volume_MA_20' in df.columns:
            indicators["volume_indicators"]["volume_ma20"] = float(latest['Volume_MA_20'])
            indicators["volume_indicators"]["volume_vs_ma20"] = float(volume / latest['Volume_MA_20'] * 100)
        
        # 波动性
        if 'ATR' in df.columns:
            indicators["volatility_indicators"]["atr"] = float(latest['ATR'])
            indicators["volatility_indicators"]["atr_percent"] = float(latest['ATR'] / close * 100)
        
        return indicators
    
    def _analyze_price(self, df: pd.DataFrame) -> Dict[str, Any]:
        """价格分析"""
        if df.empty:
            return {}
        
        close = df['Close']
        analysis = {
            "price_range": {
                "high_1mo": float(df['High'].max()),
                "low_1mo": float(df['Low'].min()),
                "avg_close": float(close.mean()),
                "volatility": float(close.std())
            },
            "trend_analysis": {},
            "key_levels": []
        }
        
        # 趋势分析
        for days in [20, 30]:
            if len(df) >= days:
                recent = close.iloc[-days:]
                trend = (recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0] * 100
                analysis["trend_analysis"][f"trend_{days}_days"] = float(trend)
        
        # 关键价格水平（简化版）
        current_price = close.iloc[-1]
        highs = df['High'].rolling(20, center=True).max().dropna().unique()
        lows = df['Low'].rolling(20, center=True).min().dropna().unique()
        levels = sorted(set(highs) | set(lows), reverse=True)
        analysis["key_levels"] = [float(l) for l in levels if abs(l - current_price) / current_price < 0.3][:5]
        
        return analysis


def test():
    tool = YahooFinanceTool()
    
    print("获取AAPL信息:")
    info = tool.get_stock_info("AAPL")
    print(f"  价格: ${info.current_price} ({info.change_percent:+.2f}%)")
    
    print("\n导出数据:")
    csv_path = tool.export_kline_to_csv("AAPL", period="5d", interval="1h")
    print(f"  CSV: {os.path.basename(csv_path)}")
    
    json_path = tool.export_analysis_to_json("AAPL", period="5d", interval="1h")
    print(f"  JSON: {os.path.basename(json_path)}")


if __name__ == "__main__":
    test()
