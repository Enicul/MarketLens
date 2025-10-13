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

async def run_full_debate_tools(ticker: str, risk="medium", horizon="medium", rounds: int = 3):
    analyst_out = await analyze_for_manager(ticker, ["news","fundamentals","market","sentiment"])
    bundle = to_research_bundle(analyst_out)

    # Multi-round debate state
    debate_history = []  # list of {role: "bullish"|"bearish", text: str}
    latest_bull = None
    latest_bear = None

    bull = None
    bear = None

    for r in range(max(1, rounds)):
        print(f"[Debate] Round {r+1}/{max(1, rounds)} - Bullish speaking...")
        # Bullish speaks using latest bear highlights
        bull = await bullish_research_tool.ainvoke({
            "ticker": ticker,
            "analyst_bundle": bundle,
            "latest_bear": latest_bear,
            "debate_history": debate_history
        })
        # Summarize for the next turn context
        bull_thesis = (bull or {}).get("thesis") or ""
        bull_args = (bull or {}).get("arguments", [])
        bull_text = (bull_thesis + "\n- " + "\n- ".join(bull_args[:3])).strip()
        debate_history.append({"role": "bullish", "text": bull_text})
        latest_bull = bull_thesis or ("; ".join(bull_args[:2]) if bull_args else None)

        print(f"[Debate] Round {r+1}/{max(1, rounds)} - Bearish responding...")
        # Bearish responds using latest bull highlights
        bear = await bearish_research_tool.ainvoke({
            "ticker": ticker,
            "analyst_bundle": bundle,
            "latest_bull": latest_bull,
            "debate_history": debate_history
        })
        bear_thesis = (bear or {}).get("thesis") or ""
        bear_args = (bear or {}).get("arguments", [])
        bear_text = (bear_thesis + "\n- " + "\n- ".join(bear_args[:3])).strip()
        debate_history.append({"role": "bearish", "text": bear_text})
        latest_bear = bear_thesis or ("; ".join(bear_args[:2]) if bear_args else None)

    decision = await moderate_debate_tool.ainvoke({
        "ticker": ticker,
        "bullish": bull,
        "bearish": bear,
        "risk_tolerance": risk,
        "time_horizon": horizon
    })
    return {"bullish": bull, "bearish": bear, "decision": decision, "debate_history": debate_history, "rounds": max(1, rounds)}

if __name__ == "__main__":
    result = asyncio.run(run_full_debate_tools("AAPL"))
    import json; print(json.dumps(result, indent=2))
