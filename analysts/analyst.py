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
async def analyze_for_manager(ticker: str, intent: str) -> dict:
    """
    intent ∈ {'news','fundamentals','market','sentiment'} (or any natural language;
    the prompt lets the agent route).
    Returns a dict parsed from the Analyst's JSON-only output.
    """
    # Construct a minimal, explicit input for the Analyst
    user_input = (
        f"Ticker: {ticker}\n"
        f"Intent: {intent}\n"
        f"Please perform the analysis and RETURN JSON ONLY as specified."
    )
    resp = await executor.ainvoke({"input": user_input, "history": []})
    out = resp["output"]
    try:
        return json.loads(out)
    except Exception:
        # If the model ever emits stray text, wrap it to keep contract
        return {"ticker": ticker, "channel": intent, "data": out, "summary": "Non-JSON output wrapped."}

# ---- Demo ----
async def main():
    # Simulate Main Manager passing (ticker, intent)
    tasks = [
        ("AAPL", "fundamentals"),
        # ("NVDA", "news"),
        # ("TSLA", "sentiment"),
        # ("MSFT", "market"),
    ]
    for tkr, intent in tasks:
        print(f"\n=== Manager → Analyst: {tkr} / {intent} ===")
        result = await analyze_for_manager(tkr, intent)
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
