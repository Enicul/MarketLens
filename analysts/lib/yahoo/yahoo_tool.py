import os
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import asdict
from langchain.tools import StructuredTool
from .yahoo import YahooFinanceTool


def _clean_data(obj):
    """清理空值"""
    if isinstance(obj, dict):
        return {k: _clean_data(v) for k, v in obj.items() 
                if v not in (None, "", [], {}, float("nan"))}
    if isinstance(obj, list):
        return [_clean_data(v) for v in obj 
                if v not in (None, "", [], {}, float("nan"))]
    return obj


async def get_market(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """获取市场数据和技术分析（直接返回数据，不写文件）"""
    tool = YahooFinanceTool(output_dir=output_dir or "output")
    
    hist_data = tool.get_historical_data(ticker, period, interval)
    stock_info = tool.get_stock_info(ticker)
    df = hist_data.data
    analysis = {
        "stock_basic_info": asdict(stock_info),
        "technical_indicators": tool._extract_indicators(df),
        "price_analysis": tool._analyze_price(df),
        "data_summary": {
            "historical_data_points": hist_data.data_points,
            "data_period": hist_data.period,
            "start_date": hist_data.start_date,
            "end_date": hist_data.end_date,
            "last_updated": datetime.now().isoformat()
        }
    }
    
    return _clean_data({
        "ticker": ticker,
        "period": period,
        "interval": interval,
        "retrieved_at": datetime.utcnow().isoformat(),
        **analysis  
    })


async def get_market_csv(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """获取K线数据（CSV格式）"""
    tool = YahooFinanceTool(output_dir=output_dir or "output")
    csv_path = tool.export_kline_to_csv(ticker, period, interval)
    
    return _clean_data({
        "ticker": ticker,
        "period": period,
        "interval": interval,
        "csv_path": csv_path,
        "filename": os.path.basename(csv_path),
        "size_bytes": os.path.getsize(csv_path),
        "retrieved_at": datetime.utcnow().isoformat(),
    })


# 直接定义为市场分析工具
get_market = StructuredTool.from_function(
    func=get_market,
    coroutine=get_market,
    name="get_market",
    description="获取股票市场数据和技术分析（包含价格、成交量、技术指标等）"
)

get_market_csv = StructuredTool.from_function(
    func=get_market_csv,
    coroutine=get_market_csv,
    name="get_market_csv",
    description="获取股票K线历史数据CSV文件"
)