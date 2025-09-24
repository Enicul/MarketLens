"""
Yahoo Finance 数据获取工具 - 为Market Lens Agent提供数据支持

该模块提供全面的股票数据获取功能，包括：
- 实时和历史价格数据
- 财务指标和基本面数据
- 公司信息和新闻
- 技术指标计算
- 数据验证和错误处理

Author: Market Lens Team
Date: 2025-01-21
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any, Tuple
import logging
import time
import warnings
from dataclasses import dataclass, asdict
from functools import wraps

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 忽略yfinance警告
warnings.filterwarnings('ignore', category=FutureWarning)


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"函数 {func.__name__} 在 {max_retries} 次尝试后仍然失败: {e}")
                        raise e
                    logger.warning(f"函数 {func.__name__} 第 {attempt + 1} 次尝试失败: {e}，{delay}秒后重试")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


@dataclass
class StockData:
    """股票数据结构"""
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
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class HistoricalData:
    """历史数据结构"""
    ticker: str
    data: pd.DataFrame
    period: str
    interval: str
    start_date: str
    end_date: str
    data_points: int


@dataclass
class FinancialData:
    """财务数据结构"""
    ticker: str
    income_statement: Optional[pd.DataFrame] = None
    balance_sheet: Optional[pd.DataFrame] = None
    cash_flow: Optional[pd.DataFrame] = None
    quarterly_earnings: Optional[pd.DataFrame] = None
    annual_earnings: Optional[pd.DataFrame] = None
    recommendations: Optional[pd.DataFrame] = None


class YahooFinanceTool:
    """Yahoo Finance 数据获取工具"""

    def __init__(self, timeout: int = 30, output_dir: str = "output"):
        """
        初始化工具
        
        Args:
            timeout: 请求超时时间（秒）
            output_dir: 输出目录
        """
        self.timeout = timeout
        self.output_dir = output_dir
        self.session = None
        
        # 创建输出目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.info(f"创建输出目录: {output_dir}")

    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """获取ticker对象"""
        try:
            ticker = yf.Ticker(symbol)
            # 测试连接
            info = ticker.info
            if not info or 'symbol' not in info:
                raise ValueError(f"无法获取股票 {symbol} 的信息")
            return ticker
        except Exception as e:
            logger.error(f"获取ticker {symbol} 失败: {e}")
            raise

    @retry_on_failure(max_retries=3, delay=1.0)
    def get_stock_info(self, symbol: str) -> StockData:
        """
        获取股票基本信息
        
        Args:
            symbol: 股票代码
            
        Returns:
            StockData: 股票基本信息
        """
        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info
            
            # 提取基本信息
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            previous_close = info.get('previousClose', current_price)
            change = current_price - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else 0
            
            return StockData(
                ticker=symbol.upper(),
                current_price=round(current_price, 2),
                change=round(change, 2),
                change_percent=round(change_percent, 2),
                volume=info.get('volume', 0),
                market_cap=info.get('marketCap'),
                pe_ratio=info.get('trailingPE'),
                pb_ratio=info.get('priceToBook'),
                dividend_yield=info.get('dividendYield'),
                beta=info.get('beta'),
                high_52w=info.get('fiftyTwoWeekHigh'),
                low_52w=info.get('fiftyTwoWeekLow')
            )
            
        except Exception as e:
            logger.error(f"获取股票 {symbol} 信息失败: {e}")
            raise

    @retry_on_failure(max_retries=3, delay=1.0)
    def get_historical_data(self, symbol: str, period: str = "1mo", 
                          interval: str = "1d", start: str = None, 
                          end: str = None) -> HistoricalData:
        """
        获取历史价格数据
        
        Args:
            symbol: 股票代码
            period: 时间周期 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: 数据间隔 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            
        Returns:
            HistoricalData: 历史数据对象
        """
        try:
            ticker = self._get_ticker(symbol)
            
            # 获取历史数据
            hist = ticker.history(
                period=period,
                interval=interval,
                start=start,
                end=end,
                timeout=self.timeout
            )
            
            if hist.empty:
                raise ValueError(f"未找到股票 {symbol} 的历史数据")
            
            # 数据清洗
            hist = hist.dropna()
            
            # 添加技术指标
            hist = self._add_technical_indicators(hist, period, interval)
            
            return HistoricalData(
                ticker=symbol.upper(),
                data=hist,
                period=period,
                interval=interval,
                start_date=hist.index[0].strftime('%Y-%m-%d') if not hist.empty else '',
                end_date=hist.index[-1].strftime('%Y-%m-%d') if not hist.empty else '',
                data_points=len(hist)
            )
            
        except Exception as e:
            logger.error(f"获取股票 {symbol} 历史数据失败: {e}")
            raise

    def _add_technical_indicators(self, df: pd.DataFrame, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
        """添加技术指标"""
        try:
            # 根据数据周期和间隔自适应计算MA窗口
            ma_windows = self._calculate_adaptive_ma_windows(df, period, interval)
            
            # 移动平均线簇 - 自适应窗口
            for ma_name, window in ma_windows.items():
                if window <= len(df):
                    df[ma_name] = df['Close'].rolling(window=window).mean()
                else:
                    # 如果数据点不够，使用最大可能窗口
                    max_window = max(1, len(df) // 2)
                    df[ma_name] = df['Close'].rolling(window=max_window).mean()
            
            # RSI - 自适应窗口
            rsi_window = self._calculate_rsi_window(period, interval)
            df['RSI'] = self._calculate_rsi(df['Close'], window=rsi_window)
            
            # MACD - 自适应参数
            macd_params = self._calculate_macd_params(period, interval)
            macd_line, signal_line, histogram = self._calculate_macd(
                df['Close'], 
                fast=macd_params['fast'], 
                slow=macd_params['slow'], 
                signal=macd_params['signal']
            )
            df['MACD'] = macd_line
            df['MACD_Signal'] = signal_line
            df['MACD_Histogram'] = histogram
            
            # 布林带 - 自适应窗口
            bb_window = self._calculate_bb_window(period, interval)
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(df['Close'], window=bb_window)
            df['BB_Upper'] = bb_upper
            df['BB_Middle'] = bb_middle
            df['BB_Lower'] = bb_lower
            
            # 成交量指标 - 自适应窗口
            volume_windows = self._calculate_volume_ma_windows(period, interval)
            for vol_name, window in volume_windows.items():
                if window <= len(df):
                    df[vol_name] = df['Volume'].rolling(window=window).mean()
                else:
                    max_window = max(1, len(df) // 2)
                    df[vol_name] = df['Volume'].rolling(window=max_window).mean()
            
            # 随机震荡指标 - 自适应窗口
            stoch_params = self._calculate_stochastic_params(period, interval)
            df['Stoch_K'], df['Stoch_D'] = self._calculate_stochastic(
                df, 
                k_period=stoch_params['k_period'], 
                d_period=stoch_params['d_period']
            )
            
            # 平均真实波幅 - 自适应窗口
            atr_window = self._calculate_atr_window(period, interval)
            df['ATR'] = self._calculate_atr(df, window=atr_window)
            
            return df
            
        except Exception as e:
            logger.warning(f"添加技术指标失败: {e}")
            return df

    def _calculate_adaptive_ma_windows(self, df: pd.DataFrame, period: str, interval: str) -> Dict[str, int]:
        """根据数据周期和间隔自适应计算MA窗口"""
        data_length = len(df)
        
        # 根据间隔类型确定基础窗口
        if interval in ['1m', '2m', '5m']:
            # 分钟级数据 - 短期MA
            base_windows = {'MA_5': 5, 'MA_10': 10, 'MA_20': 20, 'MA_50': 50}
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            # 小时级数据 - 中短期MA
            base_windows = {'MA_5': 5, 'MA_10': 10, 'MA_20': 20, 'MA_50': 50}
        elif interval in ['1d']:
            # 日级数据 - 标准MA
            base_windows = {'MA_5': 5, 'MA_10': 10, 'MA_20': 20, 'MA_50': 50}
        elif interval in ['5d', '1wk']:
            # 周级数据 - 长期MA
            base_windows = {'MA_5': 3, 'MA_10': 5, 'MA_20': 10, 'MA_50': 20}
        elif interval in ['1mo', '3mo']:
            # 月级数据 - 超长期MA
            base_windows = {'MA_5': 2, 'MA_10': 3, 'MA_20': 5, 'MA_50': 10}
        else:
            # 默认设置
            base_windows = {'MA_5': 5, 'MA_10': 10, 'MA_20': 20, 'MA_50': 50}
        
        # 根据数据长度调整窗口
        adaptive_windows = {}
        for name, window in base_windows.items():
            # 确保窗口不超过数据长度的1/3
            max_window = max(1, data_length // 3)
            adaptive_windows[name] = min(window, max_window)
        
        return adaptive_windows

    def _calculate_rsi_window(self, period: str, interval: str) -> int:
        """根据数据周期和间隔自适应计算RSI窗口"""
        if interval in ['1m', '2m', '5m']:
            return 14  # 分钟级数据使用标准RSI
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            return 14  # 小时级数据使用标准RSI
        elif interval in ['1d']:
            return 14  # 日级数据使用标准RSI
        elif interval in ['5d', '1wk']:
            return 7   # 周级数据使用较短RSI
        elif interval in ['1mo', '3mo']:
            return 5   # 月级数据使用很短RSI
        else:
            return 14

    def _calculate_macd_params(self, period: str, interval: str) -> Dict[str, int]:
        """根据数据周期和间隔自适应计算MACD参数"""
        if interval in ['1m', '2m', '5m']:
            return {'fast': 12, 'slow': 26, 'signal': 9}
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            return {'fast': 12, 'slow': 26, 'signal': 9}
        elif interval in ['1d']:
            return {'fast': 12, 'slow': 26, 'signal': 9}
        elif interval in ['5d', '1wk']:
            return {'fast': 6, 'slow': 13, 'signal': 5}
        elif interval in ['1mo', '3mo']:
            return {'fast': 3, 'slow': 6, 'signal': 2}
        else:
            return {'fast': 12, 'slow': 26, 'signal': 9}

    def _calculate_bb_window(self, period: str, interval: str) -> int:
        """根据数据周期和间隔自适应计算布林带窗口"""
        if interval in ['1m', '2m', '5m']:
            return 20
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            return 20
        elif interval in ['1d']:
            return 20
        elif interval in ['5d', '1wk']:
            return 10
        elif interval in ['1mo', '3mo']:
            return 5
        else:
            return 20

    def _calculate_volume_ma_windows(self, period: str, interval: str) -> Dict[str, int]:
        """根据数据周期和间隔自适应计算成交量MA窗口"""
        if interval in ['1m', '2m', '5m']:
            return {'Volume_MA_10': 10, 'Volume_MA_20': 20}
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            return {'Volume_MA_10': 10, 'Volume_MA_20': 20}
        elif interval in ['1d']:
            return {'Volume_MA_10': 10, 'Volume_MA_20': 20}
        elif interval in ['5d', '1wk']:
            return {'Volume_MA_10': 5, 'Volume_MA_20': 10}
        elif interval in ['1mo', '3mo']:
            return {'Volume_MA_10': 3, 'Volume_MA_20': 5}
        else:
            return {'Volume_MA_10': 10, 'Volume_MA_20': 20}

    def _calculate_stochastic_params(self, period: str, interval: str) -> Dict[str, int]:
        """根据数据周期和间隔自适应计算随机指标参数"""
        if interval in ['1m', '2m', '5m']:
            return {'k_period': 14, 'd_period': 3}
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            return {'k_period': 14, 'd_period': 3}
        elif interval in ['1d']:
            return {'k_period': 14, 'd_period': 3}
        elif interval in ['5d', '1wk']:
            return {'k_period': 7, 'd_period': 2}
        elif interval in ['1mo', '3mo']:
            return {'k_period': 5, 'd_period': 2}
        else:
            return {'k_period': 14, 'd_period': 3}

    def _calculate_atr_window(self, period: str, interval: str) -> int:
        """根据数据周期和间隔自适应计算ATR窗口"""
        if interval in ['1m', '2m', '5m']:
            return 14
        elif interval in ['15m', '30m', '60m', '90m', '1h']:
            return 14
        elif interval in ['1d']:
            return 14
        elif interval in ['5d', '1wk']:
            return 7
        elif interval in ['1mo', '3mo']:
            return 5
        else:
            return 14

    def _calculate_rsi(self, prices: pd.Series, window: int = 14) -> pd.Series:
        """计算RSI指标"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
        except:
            return pd.Series(index=prices.index, dtype=float)

    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        """计算MACD指标"""
        try:
            ema_fast = prices.ewm(span=fast).mean()
            ema_slow = prices.ewm(span=slow).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal).mean()
            histogram = macd_line - signal_line
            return macd_line, signal_line, histogram
        except:
            return pd.Series(index=prices.index, dtype=float), pd.Series(index=prices.index, dtype=float), pd.Series(index=prices.index, dtype=float)

    def _calculate_bollinger_bands(self, prices: pd.Series, window: int = 20, std_dev: int = 2):
        """计算布林带"""
        try:
            sma = prices.rolling(window=window).mean()
            std = prices.rolling(window=window).std()
            upper_band = sma + (std * std_dev)
            lower_band = sma - (std * std_dev)
            return upper_band, sma, lower_band
        except:
            return pd.Series(index=prices.index, dtype=float), pd.Series(index=prices.index, dtype=float), pd.Series(index=prices.index, dtype=float)

    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
        """计算随机震荡指标"""
        try:
            low_min = df['Low'].rolling(window=k_period).min()
            high_max = df['High'].rolling(window=k_period).max()
            k_percent = 100 * (df['Close'] - low_min) / (high_max - low_min)
            d_percent = k_percent.rolling(window=d_period).mean()
            return k_percent, d_percent
        except:
            return pd.Series(index=df.index, dtype=float), pd.Series(index=df.index, dtype=float)

    def _calculate_atr(self, df: pd.DataFrame, window: int = 14):
        """计算平均真实波幅 (ATR)"""
        try:
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(window=window).mean()
            return atr
        except:
            return pd.Series(index=df.index, dtype=float)

    def _calculate_key_levels(self, df: pd.DataFrame, num_levels: int = 5):
        """计算关键支撑位和阻力位"""
        try:
            if df.empty:
                return []
            
            # 获取历史高点和低点
            highs = df['High'].rolling(window=20, center=True).max()
            lows = df['Low'].rolling(window=20, center=True).min()
            
            # 找出局部高点和低点
            resistance_levels = []
            support_levels = []
            
            for i in range(20, len(df) - 20):
                if df['High'].iloc[i] == highs.iloc[i]:
                    resistance_levels.append(df['High'].iloc[i])
                if df['Low'].iloc[i] == lows.iloc[i]:
                    support_levels.append(df['Low'].iloc[i])
            
            # 合并并去重，选择最接近当前价格的水平
            all_levels = sorted(set(resistance_levels + support_levels), reverse=True)
            current_price = df['Close'].iloc[-1]
            
            # 选择最相关的价格水平
            key_levels = []
            for level in all_levels:
                if abs(level - current_price) / current_price < 0.3:  # 在30%范围内
                    key_levels.append(round(float(level), 2))
            
            return key_levels[:num_levels]
            
        except Exception as e:
            logger.warning(f"计算关键价格水平失败: {e}")
            return []

    @retry_on_failure(max_retries=3, delay=1.0)
    def get_financial_data(self, symbol: str) -> FinancialData:
        """
        获取财务数据
        
        Args:
            symbol: 股票代码
            
        Returns:
            FinancialData: 财务数据对象
        """
        try:
            ticker = self._get_ticker(symbol)
            
            # 安全地获取财务报表
            income_statement = ticker.financials if ticker.financials is not None and not ticker.financials.empty else None
            balance_sheet = ticker.balance_sheet if ticker.balance_sheet is not None and not ticker.balance_sheet.empty else None
            cash_flow = ticker.cashflow if ticker.cashflow is not None and not ticker.cashflow.empty else None
            
            # 安全地获取收益数据（避免已弃用的earnings）
            quarterly_earnings = None
            annual_earnings = None
            try:
                quarterly_earnings = ticker.quarterly_earnings if ticker.quarterly_earnings is not None and not ticker.quarterly_earnings.empty else None
                # annual_earnings = ticker.earnings  # 已弃用，跳过
            except:
                pass
            
            # 安全地获取分析师推荐
            recommendations = ticker.recommendations if ticker.recommendations is not None and not ticker.recommendations.empty else None
            
            return FinancialData(
                ticker=symbol.upper(),
                income_statement=income_statement,
                balance_sheet=balance_sheet,
                cash_flow=cash_flow,
                quarterly_earnings=quarterly_earnings,
                annual_earnings=annual_earnings,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"获取股票 {symbol} 财务数据失败: {e}")
            # 返回空的财务数据对象而不是抛出异常
            return FinancialData(ticker=symbol.upper())

    @retry_on_failure(max_retries=3, delay=1.0)
    def get_news(self, symbol: str, max_news: int = 10) -> List[Dict[str, Any]]:
        """
        获取股票相关新闻
        
        Args:
            symbol: 股票代码
            max_news: 最大新闻数量
            
        Returns:
            List[Dict]: 新闻列表
        """
        try:
            ticker = self._get_ticker(symbol)
            news = ticker.news
            
            if not news:
                return []
            
            # 格式化新闻数据
            formatted_news = []
            for item in news[:max_news]:
                formatted_news.append({
                    'title': item.get('title', ''),
                    'summary': item.get('summary', ''),
                    'publisher': item.get('publisher', ''),
                    'link': item.get('link', ''),
                    'published': item.get('providerPublishTime', 0),
                    'related_tickers': item.get('relatedTickers', [])
                })
            
            return formatted_news
            
        except Exception as e:
            logger.error(f"获取股票 {symbol} 新闻失败: {e}")
            return []

    @retry_on_failure(max_retries=3, delay=1.0)
    def get_multiple_stocks(self, symbols: List[str]) -> Dict[str, StockData]:
        """
        批量获取多只股票信息
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            Dict[str, StockData]: 股票信息字典
        """
        results = {}
        
        for symbol in symbols:
            try:
                results[symbol.upper()] = self.get_stock_info(symbol)
                time.sleep(0.1)  # 避免请求过于频繁
            except Exception as e:
                logger.error(f"获取股票 {symbol} 信息失败: {e}")
                continue
        
        return results


    def get_market_summary(self) -> Dict[str, Any]:
        """
        获取市场概况
        
        Returns:
            Dict: 市场概况数据
        """
        try:
            # 获取主要指数
            indices = {
                '^GSPC': 'S&P 500',
                '^DJI': 'Dow Jones',
                '^IXIC': 'NASDAQ',
                '^VIX': 'VIX'
            }
            
            market_data = {}
            for symbol, name in indices.items():
                try:
                    data = self.get_stock_info(symbol)
                    market_data[name] = {
                        'price': data.current_price,
                        'change': data.change,
                        'change_percent': data.change_percent
                    }
                except:
                    continue
            
            return market_data
            
        except Exception as e:
            logger.error(f"获取市场概况失败: {e}")
            return {}

    def validate_symbol(self, symbol: str) -> bool:
        """
        验证股票代码是否有效
        
        Args:
            symbol: 股票代码
            
        Returns:
            bool: 是否有效
        """
        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info
            return bool(info and 'symbol' in info)
        except:
            return False

    def get_data_summary(self, symbol: str) -> Dict[str, Any]:
        """
        获取股票数据摘要
        
        Args:
            symbol: 股票代码
            
        Returns:
            Dict: 数据摘要
        """
        try:
            # 获取基本信息
            stock_info = self.get_stock_info(symbol)
            
            # 获取历史数据（最近30天）
            hist_data = self.get_historical_data(symbol, period="1mo")
            
            # 获取财务数据
            financial_data = self.get_financial_data(symbol)
            
            # 获取新闻
            news = self.get_news(symbol, max_news=5)
            
            return {
                'basic_info': asdict(stock_info),
                'historical_summary': {
                    'data_points': hist_data.data_points,
                    'period': hist_data.period,
                    'start_date': hist_data.start_date,
                    'end_date': hist_data.end_date,
                    'price_range': {
                        'high': float(hist_data.data['High'].max()) if not hist_data.data.empty else None,
                        'low': float(hist_data.data['Low'].min()) if not hist_data.data.empty else None,
                        'avg_volume': float(hist_data.data['Volume'].mean()) if not hist_data.data.empty else None
                    }
                },
                'financial_available': {
                    'income_statement': financial_data.income_statement is not None,
                    'balance_sheet': financial_data.balance_sheet is not None,
                    'cash_flow': financial_data.cash_flow is not None,
                    'earnings': financial_data.quarterly_earnings is not None
                },
                'news_count': len(news),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取股票 {symbol} 数据摘要失败: {e}")
            return {}

    def export_kline_to_csv(self, symbol: str, period: str = "1mo", 
                           interval: str = "1d", filename: str = None) -> str:
        """
        导出K线图历史数据到CSV文件
        
        Args:
            symbol: 股票代码
            period: 时间周期
            interval: 数据间隔
            filename: 自定义文件名（可选）
            
        Returns:
            str: CSV文件路径
        """
        try:
            # 获取历史数据
            hist_data = self.get_historical_data(symbol, period, interval)
            
            # 准备CSV数据
            df = hist_data.data.copy()
            df = df.reset_index()
            
            # 动态生成列名映射
            column_mapping = {
                'Date': '日期',
                'Open': '开盘价',
                'High': '最高价',
                'Low': '最低价',
                'Close': '收盘价',
                'Volume': '成交量',
                'RSI': 'RSI指标',
                'MACD': 'MACD',
                'MACD_Signal': 'MACD信号线',
                'MACD_Histogram': 'MACD柱状图',
                'BB_Upper': '布林带上轨',
                'BB_Middle': '布林带中轨',
                'BB_Lower': '布林带下轨',
                'Stoch_K': '随机指标K',
                'Stoch_D': '随机指标D',
                'ATR': '平均真实波幅'
            }
            
            # 动态添加MA列名
            for col in df.columns:
                if col.startswith('MA_'):
                    window = col.split('_')[1]
                    if interval == '1d':
                        column_mapping[col] = f'{window}日均线'
                    elif interval in ['1h', '60m']:
                        column_mapping[col] = f'{window}小时均线'
                    elif interval in ['30m']:
                        column_mapping[col] = f'{window}个30分钟均线'
                    elif interval in ['15m']:
                        column_mapping[col] = f'{window}个15分钟均线'
                    elif interval in ['5m']:
                        column_mapping[col] = f'{window}个5分钟均线'
                    elif interval in ['1wk', '5d']:
                        column_mapping[col] = f'{window}周均线'
                    elif interval in ['1mo', '3mo']:
                        column_mapping[col] = f'{window}月均线'
                    else:
                        column_mapping[col] = f'{window}期均线'
                
                # 动态添加成交量MA列名
                elif col.startswith('Volume_MA_'):
                    window = col.split('_')[2]
                    if interval == '1d':
                        column_mapping[col] = f'成交量{window}日均线'
                    elif interval in ['1h', '60m']:
                        column_mapping[col] = f'成交量{window}小时均线'
                    elif interval in ['30m']:
                        column_mapping[col] = f'成交量{window}个30分钟均线'
                    elif interval in ['15m']:
                        column_mapping[col] = f'成交量{window}个15分钟均线'
                    elif interval in ['5m']:
                        column_mapping[col] = f'成交量{window}个5分钟均线'
                    elif interval in ['1wk', '5d']:
                        column_mapping[col] = f'成交量{window}周均线'
                    elif interval in ['1mo', '3mo']:
                        column_mapping[col] = f'成交量{window}月均线'
                    else:
                        column_mapping[col] = f'成交量{window}期均线'
            
            df = df.rename(columns=column_mapping)
            
            # 格式化日期
            if '日期' in df.columns:
                df['日期'] = df['日期'].dt.strftime('%Y-%m-%d')
            
            # 设置文件名
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{symbol}_{period}_{interval}_{timestamp}.csv"
            
            if not filename.endswith('.csv'):
                filename += '.csv'
            
            filepath = os.path.join(self.output_dir, filename)
            
            # 导出CSV
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            logger.info(f"K线数据已导出到: {filepath}")
            logger.info(f"数据点数量: {len(df)}")
            
            return filepath
            
        except Exception as e:
            logger.error(f"导出K线数据到CSV失败: {e}")
            raise

    def export_analysis_to_json(self, symbol: str, period: str = "1mo", 
                               interval: str = "1d", filename: str = None) -> str:
        """
        导出关键数据到JSON文件（用于LLM分析）
        
        Args:
            symbol: 股票代码
            period: 时间周期 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: 数据间隔 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            filename: 自定义文件名（可选）
            
        Returns:
            str: JSON文件路径
        """
        try:
            # 获取历史数据（可自定义时间周期和间隔）
            hist_data = self.get_historical_data(symbol, period=period, interval=interval)
            stock_info = self.get_stock_info(symbol)
            
            # 准备分析数据
            analysis_data = {
                "stock_basic_info": {
                    "ticker": stock_info.ticker,
                    "current_price": stock_info.current_price,
                    "change": stock_info.change,
                    "change_percent": stock_info.change_percent,
                    "volume": stock_info.volume,
                    "market_cap": stock_info.market_cap,
                    "pe_ratio": stock_info.pe_ratio,
                    "pb_ratio": stock_info.pb_ratio,
                    "dividend_yield": stock_info.dividend_yield,
                    "beta": stock_info.beta,
                    "high_52w": stock_info.high_52w,
                    "low_52w": stock_info.low_52w,
                    "timestamp": stock_info.timestamp
                },
                "technical_indicators": {
                    "moving_averages": {},
                    "oscillators": {},
                    "bollinger_bands": {},
                    "volume_indicators": {},
                    "volatility_indicators": {}
                },
                "price_analysis": {
                    "price_range": {},
                    "trend_analysis": {},
                    "key_levels": []
                },
                "data_summary": {
                    "historical_data_points": hist_data.data_points,
                    "data_period": hist_data.period,
                    "start_date": hist_data.start_date,
                    "end_date": hist_data.end_date,
                    "last_updated": datetime.now().isoformat()
                }
            }
            
            # 安全地添加技术指标
            if not hist_data.data.empty:
                try:
                    current_price = hist_data.data['Close'].iloc[-1]
                    current_volume = hist_data.data['Volume'].iloc[-1]
                    
                    # 移动平均线指标
                    if 'MA_20' in hist_data.data.columns:
                        ma20 = hist_data.data['MA_20'].iloc[-1]
                        analysis_data["technical_indicators"]["moving_averages"]["ma20"] = float(ma20)
                        analysis_data["technical_indicators"]["moving_averages"]["price_vs_ma20"] = float(current_price / ma20 * 100) if ma20 != 0 else None
                    
                    if 'MA_50' in hist_data.data.columns:
                        ma50 = hist_data.data['MA_50'].iloc[-1]
                        analysis_data["technical_indicators"]["moving_averages"]["ma50"] = float(ma50)
                        analysis_data["technical_indicators"]["moving_averages"]["price_vs_ma50"] = float(current_price / ma50 * 100) if ma50 != 0 else None
                    
                    # 震荡指标
                    if 'RSI' in hist_data.data.columns:
                        analysis_data["technical_indicators"]["oscillators"]["rsi"] = float(hist_data.data['RSI'].iloc[-1])
                    
                    if 'Stoch_K' in hist_data.data.columns:
                        analysis_data["technical_indicators"]["oscillators"]["stochastic_k"] = float(hist_data.data['Stoch_K'].iloc[-1])
                    
                    if 'Stoch_D' in hist_data.data.columns:
                        analysis_data["technical_indicators"]["oscillators"]["stochastic_d"] = float(hist_data.data['Stoch_D'].iloc[-1])
                    
                    if 'MACD' in hist_data.data.columns:
                        analysis_data["technical_indicators"]["oscillators"]["macd"] = float(hist_data.data['MACD'].iloc[-1])
                    
                    # 布林带指标
                    if 'BB_Upper' in hist_data.data.columns:
                        bb_upper = hist_data.data['BB_Upper'].iloc[-1]
                        bb_lower = hist_data.data['BB_Lower'].iloc[-1]
                        analysis_data["technical_indicators"]["bollinger_bands"]["upper_band"] = float(bb_upper)
                        analysis_data["technical_indicators"]["bollinger_bands"]["lower_band"] = float(bb_lower)
                        analysis_data["technical_indicators"]["bollinger_bands"]["price_vs_upper_band"] = float(current_price / bb_upper * 100) if bb_upper != 0 else None
                    
                    # 成交量指标
                    if 'Volume_MA_20' in hist_data.data.columns:
                        volume_ma20 = hist_data.data['Volume_MA_20'].iloc[-1]
                        analysis_data["technical_indicators"]["volume_indicators"]["volume_ma20"] = float(volume_ma20)
                        analysis_data["technical_indicators"]["volume_indicators"]["volume_vs_ma20"] = float(current_volume / volume_ma20 * 100) if volume_ma20 != 0 else None
                    
                    # 波动性指标
                    if 'ATR' in hist_data.data.columns:
                        analysis_data["technical_indicators"]["volatility_indicators"]["atr"] = float(hist_data.data['ATR'].iloc[-1])
                        analysis_data["technical_indicators"]["volatility_indicators"]["atr_percent"] = float(hist_data.data['ATR'].iloc[-1] / current_price * 100) if current_price != 0 else None
                    
                    # 价格分析
                    analysis_data["price_analysis"]["price_range"] = {
                        "high_1mo": float(hist_data.data['High'].max()),
                        "low_1mo": float(hist_data.data['Low'].min()),
                        "avg_close": float(hist_data.data['Close'].mean()),
                        "volatility": float(hist_data.data['Close'].std())
                    }
                    
                    # 趋势分析
                    if len(hist_data.data) >= 20:
                        recent_20 = hist_data.data['Close'].iloc[-20:]
                        trend_20 = (recent_20.iloc[-1] - recent_20.iloc[0]) / recent_20.iloc[0] * 100
                        analysis_data["price_analysis"]["trend_analysis"]["trend_20_days"] = float(trend_20)
                    
                    if len(hist_data.data) >= 30:
                        recent_30 = hist_data.data['Close'].iloc[-30:]
                        trend_30 = (recent_30.iloc[-1] - recent_30.iloc[0]) / recent_30.iloc[0] * 100
                        analysis_data["price_analysis"]["trend_analysis"]["trend_30_days"] = float(trend_30)
                    
                    # 关键价格水平
                    key_levels = self._calculate_key_levels(hist_data.data)
                    analysis_data["price_analysis"]["key_levels"] = key_levels
                    
                except Exception as e:
                    logger.warning(f"添加技术指标时出错: {e}")
            
            # 设置文件名
            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{symbol}_analysis_{timestamp}.json"
            
            if not filename.endswith('.json'):
                filename += '.json'
            
            filepath = os.path.join(self.output_dir, filename)
            
            # 导出JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"分析数据已导出到: {filepath}")
            
            return filepath
            
        except Exception as e:
            logger.error(f"导出分析数据到JSON失败: {e}")
            raise


# 使用示例和测试函数
def example_usage():
    """使用示例"""
    print("=== Yahoo Finance 数据获取工具使用示例 ===")
    print()
    
    # 创建工具实例
    tool = YahooFinanceTool()
    
    print("1. 获取单只股票信息:")
    try:
        stock_info = tool.get_stock_info("AAPL")
        print(f"   股票: {stock_info.ticker}")
        print(f"   当前价格: ${stock_info.current_price}")
        print(f"   涨跌幅: {stock_info.change_percent:.2f}%")
        print(f"   市值: ${stock_info.market_cap:,}" if stock_info.market_cap else "   市值: 无数据")
    except Exception as e:
        print(f"   错误: {e}")
    
    print("\n2. 获取历史数据:")
    try:
        hist_data = tool.get_historical_data("AAPL", period="1mo")
        print(f"   数据点数: {hist_data.data_points}")
        print(f"   时间范围: {hist_data.start_date} 到 {hist_data.end_date}")
        print(f"   包含技术指标: RSI, MACD, 布林带, 移动平均线")
    except Exception as e:
        print(f"   错误: {e}")
    
    print("\n3. 批量获取多只股票:")
    try:
        multiple_stocks = tool.get_multiple_stocks(["AAPL", "GOOGL", "MSFT"])
        for symbol, info in multiple_stocks.items():
            print(f"   {symbol}: ${info.current_price} ({info.change_percent:+.2f}%)")
    except Exception as e:
        print(f"   错误: {e}")
    
    print("\n4. 获取市场概况:")
    try:
        market_summary = tool.get_market_summary()
        for index, data in market_summary.items():
            print(f"   {index}: {data['price']} ({data['change_percent']:+.2f}%)")
    except Exception as e:
        print(f"   错误: {e}")
    
    print("\n5. 导出K线数据到CSV:")
    try:
        #csv_path = tool.export_kline_to_csv("AAPL", period="1mo", interval="1d")
        csv_path = tool.export_kline_to_csv("AAPL", period = "1d", interval = "5m")
        print(f"   CSV文件已保存到: {csv_path}")
    except Exception as e:
        print(f"   错误: {e}")
    
    print("\n6. 导出分析数据到JSON:")
    try:
        #json_path = tool.export_analysis_to_json("AAPL", period="1mo", interval="1d")
        json_path = tool.export_analysis_to_json("AAPL", period="1d", interval="5m")
        print(f"   JSON文件已保存到: {json_path}")
    except Exception as e:
        print(f"   错误: {e}")


def test_tool():
    """测试工具功能"""
    print("=== 测试 Yahoo Finance 工具 ===")
    
    tool = YahooFinanceTool()
    
    # 测试股票代码验证
    print("测试股票代码验证:")
    test_symbols = ["AAPL", "INVALID", "GOOGL", "TSLA"]
    for symbol in test_symbols:
        is_valid = tool.validate_symbol(symbol)
        print(f"   {symbol}: {'有效' if is_valid else '无效'}")
    
    # 测试数据摘要
    print("\n测试数据摘要:")
    try:
        summary = tool.get_data_summary("AAPL")
        print(f"   基本信息: {summary.get('basic_info', {}).get('ticker', 'N/A')}")
        print(f"   历史数据点: {summary.get('historical_summary', {}).get('data_points', 0)}")
        print(f"   新闻数量: {summary.get('news_count', 0)}")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 测试数据导出
    print("\n测试数据导出:")
    try:
        # 测试CSV导出
        csv_path = tool.export_kline_to_csv("AAPL", period="1mo")
        print(f"   CSV导出成功: {os.path.basename(csv_path)}")
        
        # 测试JSON导出
        json_path = tool.export_analysis_to_json("AAPL")
        print(f"   JSON导出成功: {os.path.basename(json_path)}")
        
    except Exception as e:
        print(f"   错误: {e}")


if __name__ == "__main__":
    example_usage()
    print("\n" + "="*50)
    #test_tool()
