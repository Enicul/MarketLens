# orchestrator.py
import asyncio
from analysts.analyst import analyze_for_manager
from researchers.adapters import to_research_bundle
from researchers.bullish import bullish_research_tool
from researchers.bearish import bearish_research_tool
from researchers.debate import moderate_debate_tool

"""
Manager entry point: runs Analyst → Adapter → Bullish/Bearish Researchers → Moderator Decision.

Usage:
  python orchestrator.py --ticker AAPL --risk medium --horizon medium [--ignore-cache] [--save out.json]

Notes:
- Requires API keys in .env (Finnhub, etc.).
- Caches live under database/YYYY-MM-DD/<TICKER>/<channel>/data.json.
"""

async def run_full_debate_tools(ticker: str, risk="medium", horizon="medium"):
    analyst_out = await analyze_for_manager(ticker, ["news","fundamentals","market","sentiment"])
    bundle = to_research_bundle(analyst_out)

    bull = await bullish_research_tool.ainvoke({"ticker": ticker, "analyst_bundle": bundle})
    bear = await bearish_research_tool.ainvoke({"ticker": ticker, "analyst_bundle": bundle})

    decision = await moderate_debate_tool.ainvoke({
        "ticker": ticker,
        "bullish": bull,
        "bearish": bear,
        "risk_tolerance": risk,
        "time_horizon": horizon
    })
    return {"bullish": bull, "bearish": bear, "decision": decision}

if __name__ == "__main__":
    result = asyncio.run(run_full_debate_tools("AAPL"))
    import json; print(json.dumps(result, indent=2))
