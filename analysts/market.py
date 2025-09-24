# analysts/market.py
from langchain_core.tools import tool

from analysts.yahoo.yahoo_tool import (
    get_yahoo_analysis_json_func,
    get_yahoo_kline_csv_func,
)


# 加这里


@tool("get_market")
async def get_market(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    output_dir: str | None = None,
) -> dict:
    """
    使用 Yahoo 工具生成并返回分析 JSON 内容与元数据。

    Args:
        ticker: 股票代码
        period: 历史区间（默认 1mo）
        interval: 采样间隔（默认 1d）
        output_dir: 自定义输出目录（可选）
    """
    return await get_yahoo_analysis_json_func(
        ticker=ticker, period=period, interval=interval, output_dir=output_dir
    )


@tool("get_market_csv")
async def get_market_csv(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    output_dir: str | None = None,
) -> dict:
    """
    使用 Yahoo 工具生成 K 线 CSV 并返回路径与元数据。

    Args:
        ticker: 股票代码
        period: 历史区间（默认 1mo）
        interval: 采样间隔（默认 1d）
        output_dir: 自定义输出目录（可选）
    """
    return await get_yahoo_kline_csv_func(
        ticker=ticker, period=period, interval=interval, output_dir=output_dir
    )
