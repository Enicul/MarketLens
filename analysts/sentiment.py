# analysts/sentiment.py
from langchain_core.tools import tool


# 加这里


@tool("get_sentiment")
async def get_sentiment(ticker: str) -> dict:
    """
    Fetch overall sentiment analysis for the given ticker (placeholder).
    Later we will add retrieval logic here.
    """
    return {
        "ticker": ticker,
        "channel": "sentiment",
        "note": "sentiment analysis not implemented yet"
    }
