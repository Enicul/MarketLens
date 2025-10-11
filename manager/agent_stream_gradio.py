import os
import json
import asyncio
import sys
import datetime

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
from Trader import Trader



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
        
        # 检查是否有部分分析失败，但仍有成功的数据
        successful_analyses = [k for k, v in result.get("analyses", {}).items() if v.get("error") is None]
        failed_analyses = [k for k, v in result.get("analyses", {}).items() if v.get("error") is not None]
        
        if failed_analyses and successful_analyses:
            print(f"[ANALYST] ⚠️ 部分分析失败: {', '.join(failed_analyses)} (成功: {', '.join(successful_analyses)})")
            result["partial_success"] = True
            result["failed_analyses"] = failed_analyses
            result["successful_analyses"] = successful_analyses
        elif failed_analyses and not successful_analyses:
            print(f"[ANALYST] ❌ 所有分析都失败: {', '.join(failed_analyses)}")
            result["complete_failure"] = True
        
        today = datetime.now().strftime("%Y-%m-%d")
        with open(f"database/{today}/{ticker}/analyst_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            
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
        # Parse analyst data with better error handling
        if isinstance(analyst_data, str):
            # Try to clean up potential formatting issues
            analyst_data = analyst_data.strip()
            data = json.loads(analyst_data)
        else:
            data = analyst_data
        
        if "error" in data:
            return json.dumps({"error": "Analyst数据包含错误，无法进行研究", "details": data.get("error")}, ensure_ascii=False)
        
        print(f"[RESEARCHER] 🔬 深度研究: {ticker}")
        print(f"[DEBUG] Analyst data keys: {list(data.keys())}")
        
        # Execute researcher analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(research_for_manager(ticker.upper(), data))
        loop.close()
        
        today = datetime.now().strftime("%Y-%m-%d")
        with open(f"database/{today}/{ticker}/researcher_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return json.dumps(result, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": "analyst_data格式错误，需要有效的JSON",
            "details": str(e),
            "received_type": str(type(analyst_data))
        }, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({
            "error": f"研究分析失败: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False)


@tool
def call_trader(research_data: str, csv_file_path: str = None) -> str:
    """基于Researcher报告生成交易决策，可选使用Kronos模型预测。
    
    Args:
        research_data: call_researcher返回的JSON数据（必须先调用call_researcher）
        csv_file_path: 可选，CSV文件路径（用于Kronos预测，来自analyst的market数据）
    
    Returns:
        JSON格式的交易决策卡
    """
    try:
        print(research_data)
        print(csv_file_path)
        # Parse research data with better error handling
        if isinstance(research_data, str):
            research_data = research_data.strip()
            data = json.loads(research_data)
        else:
            data = research_data
        
        if "error" in data:
            return json.dumps({"error": "Research数据包含错误，无法生成交易决策", "details": data.get("error")}, ensure_ascii=False)
        
        print(f"[TRADER] 💹 生成交易决策")
        print(f"[DEBUG] Research data keys: {list(data.keys())}")
        
        # Save researcher data directly (Trader will handle format conversion)
        import time
        workspace_dir = os.path.dirname(os.path.dirname(__file__))
        temp_dir = os.path.join(workspace_dir, '.temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = int(time.time() * 1000)
        temp_research_file = os.path.join(temp_dir, f'research_{timestamp}.json')
        
        with open(temp_research_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[DEBUG] Saved research data to: {temp_research_file}")
        
        try:
            # Initialize trader and generate decision
            trader = Trader()
            csv_files = [csv_file_path] if csv_file_path else None
            result = trader.analyze_and_decide(temp_research_file, csv_files=csv_files)
            return result
        finally:
            # Always cleanup temp file
            try:
                if os.path.exists(temp_research_file):
                    os.unlink(temp_research_file)
                    print(f"[DEBUG] Cleaned up: {temp_research_file}")
            except Exception as e:
                print(f"[DEBUG] Cleanup warning: {e}")
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": "research_data格式错误，需要有效的JSON",
            "details": str(e),
            "received_type": str(type(research_data))
        }, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({
            "error": f"交易决策生成失败: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False)

########################################
#        Main Agent Configuration      #
########################################

# 历史管理器单例（优雅的替代全局变量）
history_manager = get_history_manager()


def build_main_agent(config=None, session_id="default"):
    """Main Agent: Orchestrates conversations, maintains context, handles files, and delegates to specialized analysis agents."""
    tools = [read_file, write_file, call_analyst, call_researcher, call_trader]
    
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
         f"3. call_trader: 基于研究报告生成交易决策（可选Kronos预测）\n"
         f"4. read_file / write_file: 文件操作\n\n"
         f"🔄 推荐工作流程:\n"
         f"- 完整流程: call_analyst → call_researcher → call_trader\n"
         f"- 研究分析: call_analyst → call_researcher\n"
         f"- 快速查询: 仅 call_analyst\n\n"
         f"💡 分析类型组合建议:\n"
         f"- 全面分析: ['news','fundamentals','market','sentiment']\n"
         f"- 快速概览: ['news','market']\n"
         f"- 基本面研究: ['fundamentals','sentiment']\n\n"
         f"⚙️ 配置状态: {analysis_desc}\n\n"
         f"📌 关键注意事项:\n"
         f"- call_researcher 的 analyst_data 参数：直接传递call_analyst的完整返回值（JSON字符串）\n"
         f"- call_trader 的 research_data 参数：直接传递call_researcher的完整返回值（JSON字符串）\n"
         f"- 不要修改、解析或重新格式化工具返回的JSON数据，直接传递给下一个工具\n"
         f"- 如果用户明确只要某个步骤，可以单独执行\n"
         f"- 如果数据收集部分失败，仍有可用数据时，继续处理成功的数据\n"
         f"- 始终用中文回复用户"),
    ]
    
    # Add history messages if available (limit to last 10 exchanges)
    if history_messages:
        recent_history = history_messages[-20:]  # Last 10 exchanges (user + assistant)
        for msg in recent_history:
            role = "human" if isinstance(msg, HumanMessage) else "assistant"
            # 转义花括号以避免模板解析错误
            content = msg.content.replace('{', '{{').replace('}', '}}')
            messages.append((role, content))
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
    print("\n" + "="*60)
    print("🚀 Market Lens AI - Gradio Interface Starting...")
    print("="*60)
    
    demo = create_chatbot()
    # 启动时清空历史
    history_manager.clear()
    
    print("✅ Gradio interface ready!")
    print("📱 Access at: http://localhost:7860")
    print("📋 Application logs will appear below:")
    print("-"*60)
    
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False, 
        debug=False  # 关闭debug模式减少日志
    )