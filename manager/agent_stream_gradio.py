import os
import json
import asyncio
import sys

from shcema import StockAnalysisInput

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from gradio_chatbox import MarketLensChatbox
from chat_history_manager import get_history_manager

# Import the real financial analysis Agent
from analysts.analyst import analyze_for_manager
from researchers.manager import research_for_manager



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
#      Stock Analysis Tools (独立工具)   #
########################################

# Global configuration for enabled analysis types
enabled_analysis_types = {
    "news": True,
    "fundamentals": True,
    "market": True,
    "sentiment": True
}

@tool(args_schema=StockAnalysisInput)
def call_analyst(ticker: str, intents: list[str] = ["news"]) -> str:
    """收集股票数据（新闻、基本面、市场数据、情绪分析）。
    
    Args:
        ticker: 股票代码
        intents: 数据类型列表，可选: ["news", "fundamentals", "market", "sentiment"]
    
    Returns:
        JSON格式的原始数据（未经分析）
    """
    try:
        # Filter enabled analysis types
        enabled_intents = [i for i in intents if enabled_analysis_types.get(i, False)]
        disabled_intents = [i for i in intents if not enabled_analysis_types.get(i, False)]
        
        if not enabled_intents:
            return json.dumps({
                "error": "所有请求的分析类型都已禁用",
                "ticker": ticker,
                "disabled_intents": disabled_intents
            }, ensure_ascii=False)
        
        print(f"[ANALYST] 📊 收集数据: {ticker} - {', '.join(enabled_intents)}")
        if disabled_intents:
            print(f"[ANALYST] ⚠️ 跳过已禁用: {', '.join(disabled_intents)}")
        
        # Execute analyst data collection
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(analyze_for_manager(ticker.upper(), enabled_intents))
        loop.close()
        
        if disabled_intents:
            result["disabled_intents"] = disabled_intents
            
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"数据收集失败: {str(e)}"}, ensure_ascii=False)


@tool
def call_researcher(ticker: str, analyst_data: str) -> str:
    """基于Analyst数据进行深度研究，生成多空辩论和投资建议。
    
    Args:
        ticker: 股票代码
        analyst_data: call_analyst返回的JSON数据（必须先调用call_analyst）
    
    Returns:
        JSON格式的研究报告（包含多空观点、辩论、投资建议）
    """
    try:
        # Parse analyst data
        data = json.loads(analyst_data) if isinstance(analyst_data, str) else analyst_data
        
        if "error" in data:
            return json.dumps({"error": "Analyst数据包含错误，无法进行研究"}, ensure_ascii=False)
        
        print(f"[RESEARCHER] 🔬 深度研究: {ticker}")
        
        # Execute researcher analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(research_for_manager(ticker.upper(), data))
        loop.close()
        
        return json.dumps(result, ensure_ascii=False)
    except json.JSONDecodeError:
        return json.dumps({"error": "analyst_data格式错误，需要有效的JSON"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"研究分析失败: {str(e)}"}, ensure_ascii=False)

########################################
#        Main Agent Configuration      #
########################################

# 历史管理器单例（优雅的替代全局变量）
history_manager = get_history_manager()


def build_main_agent(config=None, session_id="default"):
    """Main Agent: Orchestrates conversations, maintains context, handles files, and delegates to specialized analysis agents."""
    tools = [read_file, write_file, call_analyst, call_researcher]
    
    # 使用专业的历史管理器（支持多进程同步）
    history_manager.reload()
    
    # 获取历史消息（限制为最近10轮对话）
    history_messages = history_manager.get_messages(session_id, limit=10)
    
    print(f"[DEBUG] Loading history for session: {session_id}")
    print(f"[DEBUG] Found {len(history_messages)} history messages")
    
    # Dynamic prompt based on enabled analysis types
    if config:
        enabled_types = [k for k, v in config.items() if v]
        analysis_desc = f"当前启用的分析类型: {', '.join(enabled_types)}" if enabled_types else "所有分析类型都已禁用"
    else:
        analysis_desc = "所有分析类型都已启用"
    
    # Build messages with history
    messages = [
        ("system", 
         f"你是 Market Lens AI 主 Agent，专业的金融市场分析助手。\n\n"
         f"🎯 目标: 理解用户需求 → 执行分析流程 → 交付专业洞察\n\n"
         f"📋 可用工具:\n"
         f"1. call_analyst: 收集股票原始数据（新闻/基本面/市场/情绪）\n"
         f"2. call_researcher: 基于数据进行深度研究（多空辩论+投资建议）\n"
         f"3. read_file / write_file: 文件操作\n\n"
         f"🔄 推荐工作流程:\n"
         f"- 标准分析: call_analyst → call_researcher (先收集数据，再深度研究)\n"
         f"- 快速查询: 仅 call_analyst (只需要原始数据)\n"
         f"- 二次研究: 仅 call_researcher (用户已有数据或你刚获取的数据)\n\n"
         f"💡 分析类型组合建议:\n"
         f"- 全面分析: ['news','fundamentals','market','sentiment']\n"
         f"- 快速概览: ['news','market']\n"
         f"- 基本面研究: ['fundamentals','sentiment']\n\n"
         f"⚙️ 配置状态: {analysis_desc}\n\n"
         f"📌 注意事项:\n"
         f"- call_researcher 需要 analyst_data 参数（来自 call_analyst 的输出）\n"
         f"- 如果用户明确只要某个步骤，可以单独执行\n"
         f"- 始终用中文回复用户"),
    ]
    
    # Add history messages if available (limit to last 10 exchanges)
    if history_messages:
        recent_history = history_messages[-20:]  # Last 10 exchanges (user + assistant)
        for msg in recent_history:
            role = "human" if isinstance(msg, HumanMessage) else "assistant"
            messages.append((role, msg.content))
            print(f"[DEBUG] Added history: {role[:4]}: {msg.content[:50]}...")
    
    # Add placeholders for current conversation
    messages.append(("human", "{input}"))
    messages.append(MessagesPlaceholder("agent_scratchpad"))
    
    prompt = ChatPromptTemplate.from_messages(messages)
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0.3, api_key='') 
    agent = create_tool_calling_agent(llm, tools, prompt)
    
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        handle_parsing_errors=True,
    )
    
    # Return a tuple with executor and session_id
    return (executor, session_id)

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
    # 启动时清空历史
    history_manager.clear()
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False, 
        debug=True
    )