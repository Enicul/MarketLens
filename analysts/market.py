# analysts/market.py
from langchain_core.tools import tool




# 加这里







@tool("get_market")
async def get_market(ticker: str) -> dict:
    """
    Fetch basic market data for the given ticker (placeholder).
    Later we will add retrieval logic here.
    """
    return {
        "ticker": ticker,
        "channel": "market",
        "note": "market data not implemented yet"
    }
