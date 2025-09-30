import os
import json
import asyncio
import sys

from shcema import StockAnalysisInput
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI
from gradio_chatbox import MarketLensChatbox

# Import the real financial analysis Agent
from analysts.analyst import analyze_for_manager



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
def analyze_stock(ticker: str, intents: list[str] = ["news"]) -> str:
    """Concurrent stock analysis tool - multiple analyses in one request.
    
    Args:
        ticker: Stock ticker symbol
        intents: List of analysis types to execute concurrently
    """
    try:
        # Filter enabled analysis types - skip disabled ones
        enabled_intents = [i for i in intents if enabled_analysis_types.get(i, False)]
        disabled_intents = [i for i in intents if not enabled_analysis_types.get(i, False)]
        
        if not enabled_intents:
            return json.dumps({
                "error": "All requested analysis types are disabled",
                "ticker": ticker,
                "disabled_intents": disabled_intents
            }, ensure_ascii=False)
        
        # Status logging for transparency
        print(f"[ANALYSIS_STATUS] 🚀 Executing {len(enabled_intents)} analyses concurrently: {', '.join(enabled_intents)}")
        if disabled_intents:
            print(f"[ANALYSIS_STATUS] ⚠️ Skipped disabled analyses: {', '.join(disabled_intents)}")
        
        # Concurrent execution - no time wasted
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(analyze_for_manager(ticker.upper(), enabled_intents))
        loop.close()
        
        # Add disabled info to result
        if disabled_intents:
            result["disabled_intents"] = disabled_intents
            
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Analysis failed: {str(e)}"}, ensure_ascii=False)

########################################
#        Main Agent Configuration      #
########################################

def build_main_agent(config=None):
    """Main Agent: Orchestrates conversations, maintains context, handles files, and delegates to specialized analysis agents."""
    tools = [read_file, write_file, analyze_stock]
    
    # Dynamic prompt based on enabled analysis types
    if config:
        enabled_types = [k for k, v in config.items() if v]
        type_names = {
            'news': 'News Analysis',
            'fundamentals': 'Fundamental Analysis',
            'market': 'Market Data Analysis',
            'sentiment': 'Sentiment Analysis'
        }
        enabled_names = [type_names.get(t, t) for t in enabled_types]
        analysis_desc = f"Currently enabled analysis types: {', '.join(enabled_names)}" if enabled_types else "All analysis types are disabled"
    else:
        analysis_desc = "All analysis types are enabled (News Analysis, Fundamental Analysis, Market Data Analysis, Sentiment Analysis)"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         f"You are the Market Lens AI Main Agent, a professional financial market analysis assistant dedicated to providing accurate, timely, and insightful stock market analysis.\n\n"
         
         f"【CORE CAPABILITIES】\n"
         f"• Multi-dimensional Stock Analysis: Integrating news dynamics, fundamental data, market performance, and market sentiment\n"
         f"• Intelligent Dialogue Understanding: Accurately identifying user intent and flexibly responding to various inquiry styles\n"
         f"• Professional Financial Expertise: Deep understanding of financial metrics, market terminology, and investment concepts\n"
         f"• Data-Driven Decision Making: Providing objective analysis based on real-time data, avoiding subjective speculation\n\n"
         f"• Always respond in Chinese (per user preference)\n"
         
         f"【WORKFLOW】\n"
         f"1. Understanding User Requirements\n"
         f"   - Identify stock tickers (supporting company names, symbols across US/Asian markets)\n"
         f"   - Determine analysis depth (quick overview vs. in-depth research)\n"
         f"   - Identify specific concerns (e.g., valuation, growth potential, risk factors)\n\n"
         
         f"2. Intelligent Analysis Strategy\n"
         f"   - Quick Inquiry: Use ['news', 'market'] for rapid response\n"
         f"   - Investment Decision: Use ['fundamentals', 'market', 'sentiment'] for comprehensive analysis\n"
         f"   - Deep Research: Use ['news', 'fundamentals', 'market', 'sentiment'] for complete analysis\n"
         f"   - Specific Needs: Select appropriate tool combinations based on user focus\n\n"
         
         f"3. Result Presentation\n"
         f"   - Lead with core conclusions, then expand with detailed analysis\n"
         f"   - Use structured formatting for easy comprehension\n"
         f"   - Highlight key metrics and important risk indicators\n"
         f"   - Provide actionable insights (for reference only)\n\n"
         
         f"【DIALOGUE TECHNIQUES】\n"
         f"• Proactive Clarification: Actively inquire about specific needs when requirements are unclear\n"
         f"• Educational Guidance: Explain technical terms to help users understand analysis results\n"
         f"• Risk Disclosure: Emphasize market risks and encourage prudent decision-making\n"
         f"• Continuous Engagement: Maintain conversation history for coherent analytical service\n\n"
         
         f"【TOOL USAGE】\n"
         f"• analyze_stock: Supports concurrent analysis - pass multiple analysis types via 'intents' parameter for maximum efficiency\n"
         f"  - news: Latest news and events\n"
         f"  - fundamentals: Financial data and fundamental analysis\n"
         f"  - market: Real-time quotes and technical indicators\n"
         f"  - sentiment: Market sentiment and social media feedback\n"
         f"• read_file/write_file: Manage analysis reports and user documents\n\n"
         
         f"【CURRENT CONFIGURATION】\n"
         f"{analysis_desc}\n\n"
         
         f"【RESPONSE PRINCIPLES】\n"
         f"• Professional yet Accessible: Explain complex concepts in clear, understandable language\n"
         f"• Objective and Balanced: Present both positive and negative factors impartially\n"
         f"• Timeliness Priority: Prioritize latest information and indicate data freshness\n"
         f"• User-Centric: Adjust response depth based on user sophistication level\n"
         f"• Maintain professional and courteous tone throughout\n\n"
         
         f"【SPECIAL HANDLING】\n"
         f"• Ticker Recognition Failure: Provide common stock suggestions or request accurate ticker\n"
         f"• Data Retrieval Failure: Explain reasons and offer alternative solutions\n"
         f"• Market Closed Periods: Indicate data timeliness, provide last trading day data\n"
         f"• Sensitive Topics: Maintain neutrality, provide factual data, avoid investment promises"),
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
