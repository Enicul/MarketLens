import os
import json
import datetime
from typing import Dict, Any, Optional

from langchain.tools import StructuredTool

from .yahoo import YahooFinanceTool


def _prune_nones(obj):
    """Recursively drop None/empty values from dicts and lists."""
    if isinstance(obj, dict):
        return {
            k: _prune_nones(v)
            for k, v in obj.items()
            if v not in (None, "", [], {}, float("nan"))
        }
    if isinstance(obj, list):
        return [
            _prune_nones(v)
            for v in obj
            if v not in (None, "", [], {}, float("nan"))
        ]
    return obj


# ---------- Core async functions (Agent will call these) ----------
async def get_yahoo_analysis_json_func(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    生成并返回 Yahoo 分析 JSON 的内容与元数据。

    Args:
        ticker: 股票代码 (如 "AAPL")
        period: 历史区间 (如 "1mo", "1d", "6mo" 等)
        interval: 采样间隔 (如 "1d", "5m", "1wk" 等)
        output_dir: 可选，自定义输出目录（默认使用 yahoo.py 内置目录）

    Returns:
        包含 JSON 内容与文件元数据的字典。
    """
    tool = YahooFinanceTool(output_dir=output_dir or "output")
    json_path = tool.export_analysis_to_json(
        symbol=ticker, period=period, interval=interval
    )

    size_bytes = os.path.getsize(json_path) if os.path.exists(json_path) else None
    content: Dict[str, Any] = {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = json.load(f)
    except Exception:
        # 如果读取失败，返回空内容但保留路径与元信息
        content = {}

    result = {
        "ticker": ticker,
        "period": period,
        "interval": interval,
        "json_path": json_path,
        "filename": os.path.basename(json_path),
        "size_bytes": size_bytes,
        "retrieved_at": datetime.datetime.utcnow().isoformat(),
        "content": content,
    }
    return _prune_nones(result)


async def get_yahoo_kline_csv_func(
    ticker: str,
    period: str = "1mo",
    interval: str = "1d",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    生成 K 线 CSV 文件并返回文件路径与元数据。

    Args:
        ticker: 股票代码 (如 "AAPL")
        period: 历史区间 (如 "1mo", "1d", "6mo" 等)
        interval: 采样间隔 (如 "1d", "5m", "1wk" 等)
        output_dir: 可选，自定义输出目录（默认使用 yahoo.py 内置目录）

    Returns:
        包含 CSV 路径与元数据的字典（不返回全文内容以避免过大负载）。
    """
    tool = YahooFinanceTool(output_dir=output_dir or "output")
    csv_path = tool.export_kline_to_csv(
        symbol=ticker, period=period, interval=interval
    )

    size_bytes = os.path.getsize(csv_path) if os.path.exists(csv_path) else None
    result = {
        "ticker": ticker,
        "period": period,
        "interval": interval,
        "csv_path": csv_path,
        "filename": os.path.basename(csv_path),
        "size_bytes": size_bytes,
        "retrieved_at": datetime.datetime.utcnow().isoformat(),
    }
    return _prune_nones(result)


# ---------- LangChain Tool wrappers ----------
get_yahoo_analysis_json = StructuredTool.from_function(
    func=get_yahoo_analysis_json_func,
    coroutine=get_yahoo_analysis_json_func,
    name="get_yahoo_analysis_json",
    description=(
        "生成并读取 Yahoo 分析 JSON（含技术指标与价格分析）并返回内容与元数据。"
        "入参：ticker、period、interval、output_dir(可选)。"
    ),
)


get_yahoo_kline_csv = StructuredTool.from_function(
    func=get_yahoo_kline_csv_func,
    coroutine=get_yahoo_kline_csv_func,
    name="get_yahoo_kline_csv",
    description=(
        "生成 Yahoo K线 CSV 并返回文件路径与元数据（不返回全文内容）。"
        "入参：ticker、period、interval、output_dir(可选)。"
    ),
)


