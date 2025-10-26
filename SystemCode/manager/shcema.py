
from pydantic import BaseModel, Field
from typing import Literal, List

class StockAnalysisInput(BaseModel):
    """Concurrent stock analysis parameters - multiple analyses in one request"""
    ticker: str = Field(description="Stock ticker symbol, e.g., AAPL, NVDA, TSLA")
    intents: List[Literal["news", "fundamentals", "market", "sentiment"]] = Field(
        default=["news"],
        description="List of analysis types to execute concurrently"
    )