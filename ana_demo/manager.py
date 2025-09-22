# manager.py
import asyncio
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage

# Import tools
from analysts.news import get_news
from analysts.fundamentals import get_fundamentals

# Load environment variables
load_dotenv()

# LLM setup
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Prompt for manager agent
prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(
            content=(
                "You are the Manager. "
                "You have two tools:\n"
                "1) get_news → use when the user asks for latest news, headlines, or summaries.\n"
                "2) get_fundamentals → use when the user asks about company basics, profile, "
                "financial metrics, or insider transactions.\n\n"
                "Always return a short, clear summary for the user after using the tools."
            )
        ),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),  # ✅ input as plain string
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

# Create agent with both tools
agent = create_openai_functions_agent(
    llm=llm,
    tools=[get_news, get_fundamentals],
    prompt=prompt,
)

executor = AgentExecutor(agent=agent, tools=[get_news, get_fundamentals], verbose=True)


async def main():
    # Conversation memory
    history = []

    queries = [
        #"Give me a quick news brief for Nvidia",
        "Show me the fundamentals of Apple",
    ]

    for q in queries:
        print(f"\n=== USER QUERY: {q} ===")
        resp = await executor.ainvoke({
            "input": q,       #  plain string
            "history": history
        })

        # Save this turn into history
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": resp["output"]})

        print("\n--- MANAGER RESPONSE ---")
        print(resp["output"])


if __name__ == "__main__":
    asyncio.run(main())
