# analyst.py
import asyncio
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage

from fundamentals import get_fundamentals
from news import get_news
from market import get_market
from sentiment import get_sentiment

load_dotenv()
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

# ---- Helper the Main Manager would call ----
async def analyze_for_manager(ticker: str, intents: list[str]) -> dict:
    """
    Concurrent multi-tool analysis with high performance execution.
    intents: Subset of ['news','fundamentals','market','sentiment']
    """
    # Tool mapping - elegant solution without if-else chains
    tools_map = {
        'news': get_news,
        'fundamentals': get_fundamentals, 
        'market': get_market,
        'sentiment': get_sentiment
    }
    
    # Concurrent execution of all analyses
    tasks = []
    for intent in intents:
        if intent in tools_map:
            tool = tools_map[intent]
            tasks.append(asyncio.create_task(
                tool.ainvoke({"ticker": ticker})
            ))
    
    # Await all results - asyncio.gather is the proper way
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Assemble results
    output = {
        "ticker": ticker,
        "analyses": {}
    }
    
    for intent, result in zip(intents, results):
        if isinstance(result, Exception):
            output["analyses"][intent] = {
                "error": str(result),
                "data": None
            }
        else:
            output["analyses"][intent] = {
                "data": result,
                "error": None
            }
    
    return output

# ---- Demo ----
async def main():
    # Test concurrent analysis - all analyses in one shot
    print("\n=== Concurrent Analysis Demo ===")
    result = await analyze_for_manager("AAPL", ["news", "fundamentals", "market", "sentiment"])
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
