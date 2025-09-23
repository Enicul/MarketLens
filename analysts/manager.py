# manager.py
import asyncio
import json
from analyst import analyze_for_manager   # helper we wrote inside analyst.py

async def main():
    # Manager chooses which stock + which analysis channel
    tasks = [
        ("AAPL", "fundamentals"),
#        ("NVDA", "news"),
#        ("TSLA", "sentiment"),
#        ("MSFT", "market"),
    ]

    for ticker, intent in tasks:
        print(f"\n=== MAIN MANAGER asking Analyst: {ticker} / {intent} ===")
        result = await analyze_for_manager(ticker, intent)
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
