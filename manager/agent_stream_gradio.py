import os
import json
import asyncio
import sys

from shcema import StockAnalysisInput

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'analysts'))

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from gradio_chatbox import MarketLensChatbox

# Import the real financial analysis Agent
from analyst import analyze_for_manager



# Removed redundant analyze_stock function, implementing all functionality directly in call_analyst

########################################
#           Main Agent Tools           #
########################################

@tool
def read_file(path: str) -> str:
    """Read text file content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"[read_file error] {e}"

@tool
def write_file(spec: str) -> str:
    """Write text file. Input as JSON: {"path": "...", "content": "..."}."""
    try:
        p = json.loads(spec)
        path = p["path"]
        content = p.get("content", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[write_file success] Written to {path} ({len(content)} chars)"
    except Exception as e:
        return f"[write_file error] {e}"

########################################
#        Stock Analysis Tool           #
########################################



# Global configuration for enabled analysis types
enabled_analysis_types = {
    "news": True,
    "fundamentals": True,
    "market": True,
    "sentiment": True
}

@tool(args_schema=StockAnalysisInput)
def analyze_stock(ticker: str, intent: str = "news") -> str:
    """Professional stock analysis tool.
    
    Args:
        ticker: Stock ticker symbol (e.g., AAPL, NVDA)
        intent: Analysis type - news, fundamentals, market, sentiment
    """
    try:
        # Check if the analysis type is enabled
        if not enabled_analysis_types.get(intent, False):
            return json.dumps({
                "error": f"Analysis type '{intent}' is currently disabled in configuration",
                "ticker": ticker,
                "channel": intent,
                "data": {},
                "summary": f"{intent.capitalize()} analysis is disabled. Please enable it in the configuration panel."
            }, ensure_ascii=False)
        
        # Status message for UI (this will be picked up by the agent executor)
        print(f"[ANALYSIS_STATUS] 🔍 Calling {intent} analysis agent for {ticker}...")
        
        # Call the financial analysis Agent directly
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(analyze_for_manager(ticker.upper(), intent))
        loop.close()
        
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Analysis failed: {str(e)}"}, ensure_ascii=False)

########################################
#        Main Agent Configuration      #
########################################

def build_main_agent(config=None):
    """Main Agent: Manages conversations, maintains context, handles files, and calls financial analysis experts."""
    tools = [read_file, write_file, analyze_stock]
    
    # Dynamic prompt based on enabled analysis types
    if config:
        enabled_types = [k for k, v in config.items() if v]
        analysis_desc = f"Currently enabled analysis types: {', '.join(enabled_types)}" if enabled_types else "All analysis types are disabled"
    else:
        analysis_desc = "All analysis types are enabled"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         f"You are the Market Lens AI Main Agent, a professional financial market analysis assistant. "
         f"Goal: Understand user's financial analysis needs -> Call professional analysis tools -> Provide clear market insights. "
         f"Guidelines:\n"
         f"1) Use the analyze_stock tool for stock analysis, which automatically identifies tickers and analysis intent.\n"
         f"2) Use read_file / write_file for file operations.\n"
         f"3) Provide professional, accurate, and insightful responses.\n"
         f"4) {analysis_desc}. Only use enabled analysis types.\n"
         f"5) When calling analysis tools, inform the user which specific agent is being invoked.\n"
         f"6) Always respond in Chinese."),
        MessagesPlaceholder("chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3, api_key='') 
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        handle_parsing_errors=True,
    )
    return executor

########################################
#            Gradio Interface          #
########################################

def create_chatbot():
    """Create the Market Lens AI chatbot interface"""
    chatbox = MarketLensChatbox()
    return chatbox.create_interface(build_main_agent, enabled_analysis_types)

########################################
#            Launch Application        #
########################################

if __name__ == "__main__":
    demo = create_chatbot()
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False, 
        debug=True
    )
