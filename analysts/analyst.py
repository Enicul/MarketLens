# analyst.py
import asyncio
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage
from .lib.fundamentals import get_fundamentals
from .lib.news import get_news
from .lib.yahoo import get_market, get_market_csv
from .lib.X_search import get_sentiment  

# Setup environment and path
load_dotenv()
sys.path.append(os.path.dirname(__file__))


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# --- Prompt: called by a Main Manager; return JSON-only ---
prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            content=(
                "You are the Analyst, invoked by a Main Manager.\n"
                "You will receive a single stock ticker and an analysis intent.\n\n"
                "Available tools:\n"
                "1) get_news → latest headlines/summaries about a ticker or company.\n"
                "2) get_fundamentals → company basics, key financial metrics, insiders.\n"
                "3) get_market → market/price/quote/volume/trading-session context.\n"
                "4) get_sentiment → overall sentiment/stance beyond single-article headlines.\n\n"
                "Routing rules:\n"
                "- Choose exactly one tool unless the request clearly asks for multiple.\n"
                "- If multiple are requested, call them sequentially then summarize jointly.\n"
                "- Prefer get_news for specific events; get_sentiment for broader mood.\n\n"
                "OUTPUT FORMAT REQUIREMENT:\n"
                "Return JSON ONLY with keys exactly:\n"
                "  ticker: the input ticker (string)\n"
                "  channel: one of ['news','fundamentals','market','sentiment']\n"
                "  data: the raw JSON returned by the tool you called\n"
                "  summary: a short, clear 1-3 line summary for the Manager\n"
            )
        ),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

agent = create_openai_functions_agent(
    llm=llm,
    tools=[get_news, get_fundamentals, get_market, get_sentiment],
    prompt=prompt,
)

executor = AgentExecutor(
    agent=agent,
    tools=[get_news, get_fundamentals, get_market, get_sentiment],
    verbose=True,
    handle_parsing_errors=True,
)

# ---- Cache management ----
def _get_cache_path(date: str, ticker: str, intent: str) -> Path:
    """Generate cache path. Simple and deterministic."""
    return Path(f"database/{date}/{ticker}/{intent}/data.json")

def _load_from_cache(ticker: str, intent: str) -> dict | None:
    """Load cached data if exists and fresh (same day)."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path = _get_cache_path(today, ticker, intent)
    
    if cache_path.exists():
        with open(cache_path, 'r') as f:
            return json.load(f)
    return None

def _save_to_cache(ticker: str, intent: str, data: dict) -> None:
    """Save data to cache. Create dirs if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path = _get_cache_path(today, ticker, intent)
    
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---- Helper the Main Manager would call ----
async def analyze_for_manager(ticker: str, intents: list[str]) -> dict:
    """
    Direct CSV generation with market analysis caching.
    Always generates CSV file to database/{date}/{ticker}/market_csv/ folder.
    intents: Subset of ['news','fundamentals','market','sentiment']
    """
    print(f"\n[ANALYST] 🚀 Starting analysis for {ticker} - {', '.join(intents)}")
    print("-" * 50)
    
    # 创建database目录结构
    today = datetime.now().strftime("%Y-%m-%d")
    # 确保路径相对于项目根目录
    project_root = Path(__file__).resolve().parents[1]  
    csv_output_dir = project_root / "database" / today / ticker / "market_csv"
    csv_output_dir.mkdir(parents=True, exist_ok=True)
    
    # 直接调用get_market_csv生成CSV文件
    print(f"[CSV] 📊 Generating market data CSV for {ticker}")
    try:
        csv_result = await get_market_csv.ainvoke({
            "ticker": ticker,
            "period": "3mo",
            "interval": "1d",
            "output_dir": str(csv_output_dir)
        })
        print(f"[CSV] ✅ {ticker} - CSV saved to: {csv_result['csv_path']}")
        
    except Exception as e:
        print(f"[CSV] ❌ {ticker} - Failed to generate CSV: {e}")
        csv_result = {"error": str(e)}
    
    # Tool mapping for other analyses
    tools_map = {
        'news': get_news,
        'fundamentals': get_fundamentals, 
        'market': get_market,
        'sentiment': get_sentiment
    }
    
    # Prepare tasks - only for non-cached intents
    tasks = []
    task_intents = []
    cached_results = {}
    
    for intent in intents:
        if intent not in tools_map:
            continue
            
        # Check cache first - why waste API calls?
        cached = _load_from_cache(ticker, intent)
        if cached:
            cached_results[intent] = cached
            print(f"[CACHE HIT] {ticker}/{intent} - using cached data")
        else:
            tool = tools_map[intent]
            print(f"[START] {ticker}/{intent} - calling {tool.name}")
            tasks.append(asyncio.create_task(
                tool.ainvoke({"ticker": ticker})
            ))
            task_intents.append(intent)
            print(f"[CACHE MISS] {ticker}/{intent} - fetching fresh data")
    
    # Execute only necessary tasks
    fresh_results = []
    if tasks:
        print(f"[PROCESSING] {len(tasks)} tools running...")
        fresh_results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"[COMPLETE] {len(fresh_results)} tools finished")
    
    # Assemble results
    output = {
        "ticker": ticker,
        "csv_generation": csv_result,  # 添加CSV生成结果
        "analyses": {}
    }
    
    # Add cached results
    for intent, data in cached_results.items():
        output["analyses"][intent] = {
            "data": data,
            "error": None,
            "cached": True
        }
    
    # Add fresh results and save to cache
    for intent, result in zip(task_intents, fresh_results):
        if isinstance(result, Exception):
            print(f"[ERROR] {ticker}/{intent} - {str(result)[:50]}...")
            output["analyses"][intent] = {
                "error": str(result),
                "data": None,
                "cached": False
            }
        else:
            print(f"[SUCCESS] {ticker}/{intent} - data collected")
            output["analyses"][intent] = {
                "data": result,
                "error": None,
                "cached": False
            }
            # Save successful results to cache
            _save_to_cache(ticker, intent, result)
    
    print(f"[ANALYST] ✅ Analysis complete for {ticker}")
    print("=" * 50)
    return output

# ---- Demo ----
async def main():
    # Test concurrent analysis - all analyses in one shot
    print("\n=== Concurrent Analysis Demo ===")
    result = await analyze_for_manager("AAPL", ["news", "fundamentals", "market", "sentiment"])
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Test concurrent analysis with caching
    print("\n=== Concurrent Analysis Demo with Caching ===")
    
    # First call - all cache misses
    print("\n[First Call - Expect all CACHE MISS]")
    result1 = await analyze_for_manager("AAPL", ["news", "fundamentals", "market", "sentiment"])
    print(f"Cached items: {sum(1 for a in result1['analyses'].values() if a.get('cached'))}")
    
    # Second call - all cache hits
    print("\n[Second Call - Expect all CACHE HIT]")
    result2 = await analyze_for_manager("AAPL", ["news", "fundamentals", "market", "sentiment"])
    print(f"Cached items: {sum(1 for a in result2['analyses'].values() if a.get('cached'))}")
    
    # Partial call - mixed hits
    print("\n[Third Call - Mixed cache status]")
    result3 = await analyze_for_manager("NVDA", ["news", "market"])  # New ticker
    print(json.dumps(result3, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())