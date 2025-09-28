# test_researchers_sentiment_integration.py (project root)
import asyncio, json, os
from analysts.analyst import analyze_for_manager
from researcher.adapters import to_research_bundle
from researcher.bullish import BullishResearcher
from researcher.bearish import BearishResearcher

TICKER = "AAPL"

async def main():
    # OPTIONAL: clear the error cache for today’s sentiment so we fetch fresh
    from datetime import datetime
    from pathlib import Path
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path = Path(f"database/{today}/{TICKER}/sentiment/data.json")
    if cache_path.exists():
        cache_path.unlink()  # comment out if you don’t want to clear cache

    analyst_out = await analyze_for_manager(TICKER, ["news","fundamentals","market","sentiment"])
    bundle = to_research_bundle(analyst_out)

    bull = await BullishResearcher().run(ticker=TICKER, analyst_bundle=bundle)
    bear = await BearishResearcher().run(ticker=TICKER, analyst_bundle=bundle)

    def senti_evs(pack):
        return [e for e in pack.get("evidence_map", []) if e.get("source") == "sentiment"]

    print("Analyst sentiment summary:",
          bundle.get("sentiment", {}).get("overall_sentiment"),
          bundle.get("sentiment", {}).get("sentiment_score"))
    print("\nBullish sentiment evidence:", senti_evs(bull))
    print("Bearish sentiment evidence:", senti_evs(bear))

if __name__ == "__main__":
    asyncio.run(main())
