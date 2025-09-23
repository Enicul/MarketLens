
from pydantic import BaseModel, Field
from typing import Literal

class StockAnalysisInput(BaseModel):
    """Input parameters for stock analysis"""
    ticker: str = Field(description="Stock ticker symbol, e.g., AAPL, NVDA, TSLA")
    intent: Literal["news", "fundamentals", "market", "sentiment"] = Field(
        default="news",
        description="Analysis type: news (latest news), fundamentals (financial metrics), market (price data), sentiment (market sentiment)"
    )