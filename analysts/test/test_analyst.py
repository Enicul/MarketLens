import asyncio
import json
import sys
from pathlib import Path


# 确保项目根在 sys.path（便于直接运行本文件）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def run_sentiment(ticker: str, max_tweets=None, headless=None) -> dict:
    """调用 X/Twitter 舆情工具，返回统一 JSON 结构。"""
    from analysts.lib.X_search.tool import get_sentiment as x_get_sentiment

    # 直接调用工具的异步接口；返回为字典
    data = await x_get_sentiment.coroutine(ticker=ticker)
    
    # get_sentiment 已经返回标准化的字典结构
    summary = f"{ticker} tweets: {data.get('metrics', {}).get('total_tweets', 0)}" if isinstance(data, dict) else ""
    return {
        "ticker": ticker,
        "channel": "sentiment",
        "data": data,
        "summary": summary,
    }


def accept_like_analyst(raw_output, ticker: str, intent: str) -> dict:
    """按 analysts/analyst.py 的规则解析输出，验证是否可被接收。"""
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

    # 仅调用 sentiment，并打印原始输出（工具返回的 JSON 字符串）
    raw = await run_sentiment(ticker)
    print("=== Raw sentiment result (already normalized) ===")
    print(json.dumps(raw, ensure_ascii=False, indent=2))


    accepted = accept_like_analyst(raw, ticker, intent)
    print("\n=== Accepted by analyst rules ===")
    print(json.dumps(accepted, ensure_ascii=False, indent=2))

    # # 测试 market 工具：调用并验证可被 analyst 规则接收
    # from analysts.market import get_market
    #
    # ticker = "TSLA"
    # intent = "market"
    #
    # # 原始调用（返回 dict）
    # raw_data = await get_market.coroutine(ticker=ticker, period="1mo", interval="1d")
    # print("=== Raw market result ===")
    # print(json.dumps(raw_data, ensure_ascii=False, indent=2))
    #
    # accepted = accept_like_analyst(raw_data, ticker, intent)
    # print("\n=== Accepted by analyst rules ===")
    # print(json.dumps(accepted, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())


