import os
import json
import asyncio
import sys
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from manager.shcema import StockAnalysisInput

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# 配置日志级别，减少HTTP请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
# from langchain_openai import ChatOpenAI  # 如需使用 OpenAI 请取消注释
from config import LLM_GOOGLE
from manager.gradio_chatbox import MarketLensChatbox

# Import the real financial analysis Agent
from analysts.analyst import analyze_for_manager
from researchers.manager import research_for_manager
from Trader import Trader
from risk_management.orchestrator import run_risk_management
from risk_management.utils import TraderDataError

from manager.memory_manager import ToolAwareConversationMemory


# Removed redundant analyze_stock function, implementing all functionality directly in call_analyst
def _format_percentage(value: Optional[float], default: str = "—") -> str:
    if value is None:
        return default
    return f"{value * 100:.1f}%"


def _extract_price(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        return value.get("price")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def format_risk_readout(
    report_or_path: Any,
    ticker: str,
    trader_text: Optional[str] = None
) -> str:
    """Convert risk-management output into a user-facing summary without exposing file paths."""
    report: Dict[str, Any]
    if isinstance(report_or_path, str):
        try:
            with open(report_or_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception:
            report = {}
    elif isinstance(report_or_path, dict):
        report = report_or_path
    else:
        report = {}

    trader_decision = report.get("trader_decision") or {}
    synthesis = report.get("synthesis") or {}
    execution = synthesis.get("execution") or {}
    follow_up = synthesis.get("follow_up") or []
    risk_budget = synthesis.get("risk_budget")
    confidence = synthesis.get("confidence")
    action = execution.get("action") or synthesis.get("summary")
    position_size = execution.get("position_size")
    stop_loss = _extract_price(execution.get("stop_loss"))
    take_profit = _extract_price(execution.get("take_profit"))
    hedging = execution.get("hedging_ideas") or []
    rationale = synthesis.get("rationale") or []

    direction = trader_decision.get("decision")
    current_price_raw = trader_decision.get("current_price")
    try:
        current_price = float(current_price_raw) if current_price_raw is not None else None
    except (TypeError, ValueError):
        current_price = None

    lines = [
        f"{ticker.upper()} 风险管理结论：{action or '维持现有仓位，紧盯关键风险信号。'}"
    ]

    summary_parts = []
    if direction:
        summary_parts.append(f"交易方向 {direction}")
    if confidence is not None:
        summary_parts.append(f"风险置信度 {confidence * 100:.1f}%")
    if risk_budget:
        summary_parts.append({
            "low": "保守预算",
            "medium": "中性预算",
            "high": "积极预算",
        }.get(risk_budget, str(risk_budget)))
    if summary_parts:
        lines.append("，".join(summary_parts))

    if position_size is not None:
        lines.append(f"建议仓位：{_format_percentage(position_size)}")
    if current_price is not None:
        lines.append(f"当前价格：{current_price:.2f}")
    if stop_loss is not None:
        lines.append(f"止损：{stop_loss:.2f}")
    if take_profit is not None:
        lines.append(f"止盈：{take_profit:.2f}")

    if hedging:
        lines.append("风险对冲建议：" + "；".join(hedging[:2]))

    if follow_up:
        lines.append("跟踪要点：" + "；".join(follow_up[:3]))
    elif rationale:
        lines.append("关键理由：" + "；".join(rationale[:2]))
    elif trader_text:
        lines.append(trader_text.strip())

    return "\n".join(lines)

########################################
#           Main Agent Tools           #
########################################

@tool
def call_risk_manager(ticker: str, trader_data: str, include_raw: bool = False) -> str:
    """Run multi-perspective risk management on trader output.

    Args:
        ticker: Stock ticker symbol.
        trader_data: Trader decision card JSON string or file path.
        include_raw: Set true to retain raw trader payload inside the report.

    Returns:
        JSON string summarising the risk report generation status.
    """
    snippet = trader_data.strip() if isinstance(trader_data, str) else str(trader_data)
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."
    print(f"[RISK] 🔄 调用风险管理工具，ticker={ticker}, include_raw={include_raw}")
    print(f"[RISK] 📥 trader_data 输入片段: {snippet}")
    try:
        saved_path, summary = run_risk_management(
            ticker=ticker,
            trader_data=trader_data,
            include_raw=include_raw,
        )
        print(f"[RISK] ✅ 风险报告生成成功: {saved_path}")
        print(f"[RISK] 📊 摘要: {summary}")
        return json.dumps({"status": "success", "summary": summary}, ensure_ascii=False)
    except TraderDataError as exc:
        print(f"[RISK] ❌ Trader 数据加载失败: {exc}")
        return json.dumps({"status": "error", "error_type": "TraderDataError", "message": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        import traceback
        print(f"[RISK] ❌ 风险管理模块异常: {exc}")
        traceback.print_exc()
        return json.dumps({"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}, ensure_ascii=False)

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
        
        logging.info(f"[ANALYST] 📊 收集数据: {ticker} - {', '.join(enabled_intents)}")
        if disabled_intents:
            logging.warning(f"[ANALYST] ⚠️ 跳过已禁用: {', '.join(disabled_intents)}")
        
        # Execute analyst data collection
        result = asyncio.run(analyze_for_manager(ticker.upper(), enabled_intents))
        
        if disabled_intents:
            result["disabled_intents"] = disabled_intents
        
        # 检查是否有部分分析失败，但仍有成功的数据
        successful_analyses = [k for k, v in result.get("analyses", {}).items() if v.get("error") is None]
        failed_analyses = [k for k, v in result.get("analyses", {}).items() if v.get("error") is not None]

        print(f"[ANALYST] successful_analyses: {successful_analyses}")
        
        if failed_analyses and successful_analyses:
            print(f"[ANALYST] ⚠️ 部分分析失败: {', '.join(failed_analyses)} (成功: {', '.join(successful_analyses)})")
            result["partial_success"] = True
            result["failed_analyses"] = failed_analyses
            result["successful_analyses"] = successful_analyses
        elif failed_analyses and not successful_analyses:
            print(f"[ANALYST] ❌ 所有分析都失败: {', '.join(failed_analyses)}")
            result["complete_failure"] = True
        today = datetime.now().strftime("%Y-%m-%d")
        analyst_data_path = f"database/{today}/{ticker}/analyst_{ticker}.json"
        with open(analyst_data_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return analyst_data_path
    except Exception as e:
        return json.dumps({"error": f"数据收集失败: {str(e)}"}, ensure_ascii=False)


@tool
async def call_researcher(ticker: str, analyst_data_path: str) -> str:
    """基于Analyst数据进行深度研究，生成多空辩论和投资建议。
    
    Args:
        ticker: 股票代码
        analyst_data_path: call_analyst返回的JSON数据文件路径（必须先调用call_analyst）
    
    Returns:
        JSON格式的研究报告（包含多空观点、辩论、投资建议）
    """
    try:
        # Try to clean up potential formatting issues
        analyst_data_path = analyst_data_path.strip()

        def _read_json(path: str):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        data = await asyncio.to_thread(_read_json, analyst_data_path)
        
        if "error" in data:
            return json.dumps({"error": "Analyst数据包含错误，无法进行研究", "details": data.get("error")}, ensure_ascii=False)
        
        logging.info(f"[RESEARCHER] 🔬 深度研究: {ticker}")
        logging.debug(f"[DEBUG] Analyst data keys: {list(data.keys())}")
        
        # Execute researcher analysis
        result = await research_for_manager(ticker.upper(), data)
        today = datetime.now().strftime("%Y-%m-%d")
        researcher_data_path = f"database/{today}/{ticker}/researcher_{ticker}.json"

        def _write_json(path: str, payload: Dict[str, Any]):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write_json, researcher_data_path, result)

        return researcher_data_path
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": "analyst_data格式错误，需要有效的JSON",
            "details": str(e),
            "received_type": str(type(researcher_data_path))
        }, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({
            "error": f"研究分析失败: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False)


@tool
def call_trader(ticker: str, research_data_path: str, csv_file_path: str = None, user_request: str = "") -> str:
    """基于Researcher报告生成交易决策，可选使用Kronos模型预测。
    
    Args:
        ticker: 股票代码
        research_data_path: call_researcher返回的JSON数据文件路径（必须先调用call_researcher）
        csv_file_path: 可选，CSV文件路径（用于Kronos预测，来自analyst的market数据）
        user_request: 用户的原始请求，用于判断是否需要Kronos预测
    
    Returns:
        JSON格式的交易决策卡
    """
    try:
        research_data_path = research_data_path.strip()
        with open(research_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "error" in data:
            return json.dumps({"error": "Research数据包含错误，无法生成交易决策", "details": data.get("error")}, ensure_ascii=False)
        
        logging.info("[TRADER] 💹 生成交易决策")
        logging.debug(f"[DEBUG] Research data keys: {list(data.keys())}")
        
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
            
            # 构建包含用户请求的完整请求
            trader_request = f"请基于研究结论生成交易决策卡。研究文件: {temp_research_file}"
            if user_request:
                trader_request += f"\n用户原始请求: {user_request}"
            if csv_files:
                trader_request += f"\nCSV文件: {', '.join(csv_files)}"
            
            result = trader.process_request(trader_request, temp_research_file, csv_files)
            today = datetime.now().strftime("%Y-%m-%d")
            trader_data_path = f"database/{today}/{ticker}/trader_{ticker}.json"
            with open(trader_data_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[TRADER] 📁 交易决策已保存至 {trader_data_path}")

            trader_notes = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

            # Automatically trigger risk management using saved trader output
            human_readout = None
            risk_meta: Dict[str, Any] = {}
            try:
                risk_path, risk_summary = run_risk_management(
                    ticker=ticker,
                    trader_data=trader_data_path,
                    include_raw=False,
                )
                risk_meta = {k: v for k, v in risk_summary.items() if k != "saved_path"}
                human_readout = format_risk_readout(risk_path, ticker, trader_text=trader_notes)
            except Exception as risk_exc:
                print(f"[RISK] ⚠️ 自动风险管理失败: {risk_exc}")
                risk_meta = {"risk_error": str(risk_exc)}
                trader_excerpt = trader_notes
                human_readout = (
                    f"{ticker.upper()} 风险模块暂不可用，请谨慎观望。"
                    f"交易建议概要：{trader_excerpt[:200]}..."
                )
                risk_meta.setdefault("warning", "自动风控失败，仅供参考")

            if not human_readout:
                human_readout = f"{ticker.upper()} 交易建议概要：{trader_notes[:200]}..."

            response_payload: Dict[str, Any] = {
                "status": "success",
                "trader_notes": trader_notes,
                "human_readout": human_readout,
            }
            response_payload.update(risk_meta)
            return json.dumps(response_payload, ensure_ascii=False)
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
            "received_type": str(type(research_data_path))
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

def build_main_agent(config=None, memory: ToolAwareConversationMemory | None = None):
    """创建一个带 LangChain 原生记忆的 AgentExecutor。"""
    tools = [read_file, write_file, call_analyst, call_researcher, call_trader, call_risk_manager]
    
    # 动态配置描述
    if config:
        enabled_types = [k for k, v in config.items() if v]
        analysis_desc = f"当前启用：{', '.join(enabled_types)}" if enabled_types else "所有分析类型都已禁用"
    else:
        analysis_desc = "所有分析类型都已启用"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "你是 Market Lens AI 主代理，专业的金融市场分析助手。\n\n"
         "🎯 目标：理解用户需求，执行分析流程，交付专业洞察。\n\n"
         "📋 可用工具：\n"
         "1. call_analyst：收集股票原始数据（新闻 / 基本面 / 市场 / 情绪）。\n"
         "2. call_researcher：基于数据进行深度研究（多空辩论、投资建议）。\n"
         "3. call_trader：生成交易决策，支持user_request参数传递用户需求。\n"
         "4. call_risk_manager：必要时单独复查风险（默认流程已自动执行）。\n"
         "5. read_file / write_file：文件操作。\n\n"
         "🔄 推荐工作流程：\n"
         "- 完整流程：call_analyst → call_researcher → call_trader。\n"
         "- 研究分析：call_analyst → call_researcher。\n"
         "- 快速查询：call_analyst。\n\n"
         "⚠️ 回复要求：\n"
         "- 不得在用户回复中暴露任何文件路径或内部存储位置。\n"
         "- 当工具返回 human_readout 字段时，优先引用其中要点作为答复核心。\n"
         "- 输出需具体可执行：包含方向、仓位、止损 / 止盈、触发条件等关键数值。\n"
         "- 若风控失败，需提醒谨慎并说明已知的交易要点。\n\n"
         f"⚙️ 配置状态：{analysis_desc}\n\n"
         "📌 关键注意事项：\n"
         "- 传递工具返回的 JSON，不要擅自删改字段。\n"
         "- 调用call_trader时，将用户的原始请求通过user_request参数传递。\n"
         "- 如果用户要求预测/价格预测/未来走势/Kronos，务必在user_request中体现。\n"
         "- 如果部分分析失败但仍有可用数据，也要继续处理并提示缺口。\n"
         "- 全程使用中文回复用户。"),
MessagesPlaceholder("messages"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad")
    ])
    
    llm = LLM_GOOGLE
    agent = create_tool_calling_agent(llm, tools, prompt)

    if memory is None:
        memory = ToolAwareConversationMemory(
            memory_key="messages",
            return_messages=True,
            input_key="input",
        )

    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
    )

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
    
    print("✅ Gradio interface ready!")
    print("📱 Access at: http://localhost:7860")
    print("📋 Application logs will appear below:")
    print("-"*60)
    
    demo.launch(
        server_name="0.0.0.0", 
        server_port=7860, 
        share=False, 
        debug=False
    )
