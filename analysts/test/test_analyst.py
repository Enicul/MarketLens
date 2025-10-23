import asyncio
import json
import sys
from pathlib import Path


# make this file directly runnable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def run_sentiment(ticker: str, max_tweets=None, headless=None) -> dict:
    """Invoke X/Twitter sentiment tool, return standardized JSON structure."""
    from analysts.lib.X_search.tool import get_sentiment as x_get_sentiment

    # invoke async interface of tool, return as dictionary
    data = await x_get_sentiment.coroutine(ticker=ticker)
    
    # get_sentiment already returns standardized dictionary structure
    summary = f"{ticker} tweets: {data.get('metrics', {}).get('total_tweets', 0)}" if isinstance(data, dict) else ""
    return {
        "ticker": ticker,
        "channel": "sentiment",
        "data": data,
        "summary": summary,
    }


def accept_like_analyst(raw_output, ticker: str, intent: str) -> dict:
    """Verify if output is accepted by analysts/analyst.py rules."""
    out = raw_output
    if isinstance(out, dict):
        return out
    if isinstance(out, list):
        return {"ticker": ticker, "channel": intent, "data": out, "summary": ""}
    if isinstance(out, str):
        try:
            return json.loads(out)
        except Exception:
            text = out.strip()
            first_line = text.splitlines()[0].strip() if text else ""
            if len(first_line) > 200:
                first_line = first_line[:200] + "..."
            return {"ticker": ticker, "channel": intent, "data": text, "summary": first_line}
    text = str(out)
    return {"ticker": ticker, "channel": intent, "data": text, "summary": text[:200] + ("..." if len(text) > 200 else "")}


async def main():
    ticker = "TSLA"
    intent = "sentiment"

    # invoke only sentiment, and print raw output (JSON string returned by tool)
    raw = await run_sentiment(ticker)
    print("=== Raw sentiment result (already standardized) ===")
    print(json.dumps(raw, ensure_ascii=False, indent=2))


    accepted = accept_like_analyst(raw, ticker, intent)
    print("\n=== Accepted by Analyst rules ===")
    print(json.dumps(accepted, ensure_ascii=False, indent=2))

    # # test market tool: invoke and verify if accepted by Analyst rules
    # from analysts.market import get_market
    #
    # ticker = "TSLA"
    # intent = "market"
    #
    # # raw invoke (return dict)
    # raw_data = await get_market.coroutine(ticker=ticker, period="1mo", interval="1d")
    # print("=== Raw market result ===")
    # print(json.dumps(raw_data, ensure_ascii=False, indent=2))
    #
    # accepted = accept_like_analyst(raw_data, ticker, intent)
    # print("\n=== Accepted by Analyst rules ===")
    # print(json.dumps(accepted, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())


