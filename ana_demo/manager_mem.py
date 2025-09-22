# manager_mem.py
# Run:  python -m asyncio manager_mem.py
# Or:   python manager_mem.py --summary         (to test summary memory)
#       python manager_mem.py --k 6             (to change window size)
#       python manager_mem.py --rounds 3        (2 or 3 rounds)

import argparse
import asyncio
from typing import List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage

# Memory options
from langchain.memory import (
    ConversationBufferWindowMemory,
    ConversationSummaryMemory,
)

# --- Your tools ---
from analysts.news import get_news
from analysts.fundamentals import get_fundamentals

load_dotenv()


def build_prompt() -> ChatPromptTemplate:
    """
    Same shape as your existing manager, but ready to accept `history` from memory.
    """
    return ChatPromptTemplate.from_messages(
        [
            SystemMessage(
                content=(
                    "You are the Manager.\n"
                    "Tools available:\n"
                    "1) get_news → for latest headlines/summaries.\n"
                    "2) get_fundamentals → for company basics, financial metrics, insiders.\n\n"
                    "Rules:\n"
                    "- Choose the right tool based on user intent.\n"
                    "- If user implies a follow-up (e.g., 'what about Nvidia?'), use prior context from history.\n"
                    "- Return a short, clear summary after using any tool.\n"
                )
            ),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )


def build_agent(llm: ChatOpenAI, prompt: ChatPromptTemplate):
    return create_openai_functions_agent(
        llm=llm,
        tools=[get_news, get_fundamentals],
        prompt=prompt,
    )


def build_memory(use_summary: bool, k_window: int, llm: ChatOpenAI):
    """
    Choose one memory implementation.
    - BufferWindow keeps last k exchanges verbatim.
    - Summary compresses older dialogue into a running synopsis.
    """
    if use_summary:
        return ConversationSummaryMemory(
            llm=llm,
            memory_key="history",
            return_messages=True,
        )
    else:
        return ConversationBufferWindowMemory(
            memory_key="history",
            k=k_window,
            return_messages=True,
        )


def default_queries(rounds: int) -> List[str]:
    """
    2–3 round script that exercises memory-based follow-ups
    (1) fundamentals AAPL
    (2) follow-up for NVDA (should infer same 'fundamentals' intent)
    (3) optional: 'now news for Tesla' to force a tool switch
    """
    base = [
        "Show me the fundamentals of Apple",
        "And what about Nvidia?",
    ]
    if rounds >= 3:
        base.append("Now give me the latest news for Tesla")
    return base[:rounds]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true", help="Use ConversationSummaryMemory instead of BufferWindow")
    parser.add_argument("--k", type=int, default=4, help="k window size for ConversationBufferWindowMemory")
    parser.add_argument("--rounds", type=int, default=3, choices=[2, 3], help="Number of turns to run")
    args = parser.parse_args()

    # LLM config: temperature=0 for reliable routing
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = build_prompt()
    agent = build_agent(llm, prompt)

    memory = build_memory(use_summary=args.summary, k_window=args.k, llm=llm)

    executor = AgentExecutor(
        agent=agent,
        tools=[get_news, get_fundamentals],
        memory=memory,          # << inject memory here
        verbose=True,           # prints tool calls / traces
        handle_parsing_errors=True,
    )

    queries = default_queries(args.rounds)

    print("\n=== RUNNING WITH MEMORY:", "SummaryMemory" if args.summary else f"BufferWindow(k={args.k})", "===\n")

    for i, q in enumerate(queries, start=1):
        print(f"\n=== ROUND {i} | USER ===")
        print(q)

        resp = await executor.ainvoke({"input": q})   # memory auto-injected
        print("\n--- MANAGER RESPONSE ---")
        print(resp["output"])

        # Inspect memory after each turn
        print("\n--- MEMORY CONTENT (debug) ---")
        # load_memory_variables returns dict with the 'history' Messages
        mem_dump = memory.load_memory_variables({})
        print(mem_dump)

    print("\n=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
