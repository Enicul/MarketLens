import os
import json
import asyncio
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from contextvars import ContextVar, Token
from manager.shcema import StockAnalysisInput

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Configure logging level to reduce HTTP noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
# from langchain_openai import ChatOpenAI  # Uncomment if you prefer OpenAI
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
        f"{ticker.upper()} Risk Management Conclusion: {action or 'Maintain current position, closely monitor key risk signals.'}"
    ]

    summary_parts = []
    if direction:
        summary_parts.append(f"Trade Direction: {direction}")
    if confidence is not None:
        summary_parts.append(f"Risk Confidence: {confidence * 100:.1f}%")
    if risk_budget:
        summary_parts.append({
            "low": "Conservative Budget",
            "medium": "Neutral Budget",
            "high": "Aggressive Budget",
        }.get(risk_budget, str(risk_budget)))
    if summary_parts:
        lines.append(", ".join(summary_parts))

    if position_size is not None:
        lines.append(f"Recommended Position: {_format_percentage(position_size)}")
    if current_price is not None:
        lines.append(f"Current Price: {current_price:.2f}")
    if stop_loss is not None:
        lines.append(f"Stop Loss: {stop_loss:.2f}")
    if take_profit is not None:
        lines.append(f"Take Profit: {take_profit:.2f}")

    if hedging:
        lines.append("Hedging Recommendations: " + "; ".join(hedging[:2]))

    if follow_up:
        lines.append("Key Follow-up Points: " + "; ".join(follow_up[:3]))
    elif rationale:
        lines.append("Key Rationale: " + "; ".join(rationale[:2]))
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
    logging.info(f"[RISK] 🔄 Calling risk management tool, ticker={ticker}, include_raw={include_raw}")
    logging.info(f"[RISK] 📥 trader_data input snippet: {snippet}")
    try:
        saved_path, summary = run_risk_management(
            ticker=ticker,
            trader_data=trader_data,
            include_raw=include_raw,
        )
        logging.info(f"[RISK] ✅ Risk report generated successfully: {saved_path}")
        logging.info(f"[RISK] 📊 Summary: {summary}")
        return json.dumps({"status": "success", "summary": summary}, ensure_ascii=False)
    except TraderDataError as exc:
        logging.error(f"[RISK] ❌ Trader data loading failed: {exc}")
        return json.dumps({"status": "error", "error_type": "TraderDataError", "message": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        import traceback
        logging.error(f"[RISK] ❌ Risk management module error: {exc}")
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
#      Stock Analysis Tools            #
########################################

# Global configuration for enabled analysis types
enabled_analysis_types = {
    "news": True,
    "fundamentals": True,
    "market": True,
    "sentiment": True
}

_analysis_config_ctx: ContextVar[Dict[str, bool]] = ContextVar(
    "analysis_config_ctx", default=enabled_analysis_types.copy()
)


def _current_analysis_config() -> Dict[str, bool]:
    try:
        return _analysis_config_ctx.get()
    except LookupError:
        return enabled_analysis_types


def push_analysis_config(config: Optional[Dict[str, bool]]) -> Token:
    if config is None:
        return _analysis_config_ctx.set(enabled_analysis_types.copy())
    return _analysis_config_ctx.set(config)


def pop_analysis_config(token: Token) -> None:
    _analysis_config_ctx.reset(token)


def _find_recent_kronos_assets(symbol: str, since: Optional[datetime] = None, tolerance: timedelta = timedelta(minutes=10)) -> Optional[Dict[str, Any]]:
    base_dir = Path("database").resolve()
    if not base_dir.exists():
        return None

    symbol = symbol.upper()
    pattern = f"*/{symbol}/Kronos_output/*_metadata_*.json"
    metadata_files = sorted(base_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not metadata_files:
        return None

    def _resolve_asset(path_str: Optional[str], meta_dir: Path) -> Optional[Dict[str, Any]]:
        if not path_str:
            return None
        raw = Path(path_str)
        if raw.is_absolute():
            full_path = raw
        else:
            raw_str = str(raw).replace("\\", "/")
            if raw_str.startswith("database/"):
                rel_part = raw_str[len("database/") :]
                full_path = base_dir / rel_part
            else:
                full_path = (base_dir / raw).resolve()
        if not full_path.exists():
            return None
        try:
            relative = full_path.resolve().relative_to(base_dir).as_posix()
        except ValueError:
            return None
        return {"full": full_path, "relative": relative}

    now = datetime.utcnow()
    window_start = since - tolerance if since else None

    for meta_path in metadata_files:
        try:
            with meta_path.open("r", encoding="utf-8") as fh:
                metadata = json.load(fh)
        except Exception:
            continue

        ts_str = metadata.get("prediction_time")
        timestamp = None
        if ts_str:
            try:
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                timestamp = None
        if timestamp is None:
            timestamp = datetime.fromtimestamp(meta_path.stat().st_mtime)

        if window_start and timestamp < window_start:
            continue
        if (now - timestamp).total_seconds() > tolerance.total_seconds() * 3:
            # Skip very old predictions
            continue

        outputs = metadata.get("output_files", {})
        plot_info = _resolve_asset(outputs.get("plot"), meta_path.parent)
        csv_info = _resolve_asset(outputs.get("csv"), meta_path.parent)
        input_info = _resolve_asset(metadata.get("input_csv"), meta_path.parent)
        if not plot_info:
            continue

        meta_info = {"full": meta_path, "relative": meta_path.relative_to(base_dir).as_posix()}
        assets = {
            "timestamp": timestamp.isoformat(),
            "plot_path": plot_info["relative"],
            "plot_url": f"/assets/{plot_info['relative']}",
            "metadata_path": meta_info["relative"],
            "metadata_url": f"/assets/{meta_info['relative']}",
            "prediction_summary": metadata.get("prediction_summary"),
        }
        if csv_info:
            assets["csv_path"] = csv_info["relative"]
            assets["csv_url"] = f"/assets/{csv_info['relative']}"
        if input_info:
            assets["input_csv_path"] = input_info["relative"]
            assets["input_csv_url"] = f"/assets/{input_info['relative']}"
        return assets

    return None

@tool(args_schema=StockAnalysisInput)
async def call_analyst(ticker: str, intents: list[str] = ["news"]) -> str:
    """Collect stock data (news, fundamentals, market data, sentiment analysis).
    
    Args:
        ticker: Stock ticker symbol
        intents: List of data types, options: ["news", "fundamentals", "market", "sentiment"]
    
    Returns:
        Raw data in JSON format (not analyzed)
    """
    try:
        config = _current_analysis_config()
        # Filter enabled analysis types
        enabled_intents = [i for i in intents if config.get(i, False)]
        disabled_intents = [i for i in intents if not config.get(i, False)]

        if not enabled_intents:
            return json.dumps({
                "error": "All requested analysis types are disabled",
                "ticker": ticker,
                "disabled_intents": disabled_intents
            }, ensure_ascii=False)
        
        logging.info(f"[ANALYST] 📊 Collecting data: {ticker} - {', '.join(enabled_intents)}")
        if disabled_intents:
            logging.warning(f"[ANALYST] ⚠️ Skipping disabled: {', '.join(disabled_intents)}")
        
        # Execute analyst data collection
        result = await analyze_for_manager(ticker.upper(), enabled_intents)
        
        if disabled_intents:
            result["disabled_intents"] = disabled_intents
        
        # Check if some analyses failed but others succeeded
        successful_analyses = [k for k, v in result.get("analyses", {}).items() if v.get("error") is None]
        failed_analyses = [k for k, v in result.get("analyses", {}).items() if v.get("error") is not None]

        logging.info(f"[ANALYST] successful_analyses: {successful_analyses}")
        
        if failed_analyses and successful_analyses:
            logging.warning(f"[ANALYST] ⚠️ Partial analysis failure: {', '.join(failed_analyses)} (succeeded: {', '.join(successful_analyses)})")
            result["partial_success"] = True
            result["failed_analyses"] = failed_analyses
            result["successful_analyses"] = successful_analyses
        elif failed_analyses and not successful_analyses:
            logging.error(f"[ANALYST] ❌ All analyses failed: {', '.join(failed_analyses)}")
            result["complete_failure"] = True
        today = datetime.now().strftime("%Y-%m-%d")
        analyst_data_path = f"database/{today}/{ticker}/analyst_{ticker}.json"
        with open(analyst_data_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return analyst_data_path
    except Exception as e:
        logging.error(f"[ANALYST] ❌ Data collection failed: {str(e)}")
        return json.dumps({"error": f"Data collection failed: {str(e)}"}, ensure_ascii=False)


@tool
async def call_researcher(ticker: str, analyst_data_path: str) -> str:
    """Conduct in-depth research based on Analyst data, generate bull/bear debate and investment recommendations.
    
    Args:
        ticker: Stock ticker symbol
        analyst_data_path: JSON data file path returned by call_analyst (must call call_analyst first)
    
    Returns:
        Research report in JSON format (includes bull/bear views, debate, investment recommendations)
    """
    try:
        # Try to clean up potential formatting issues
        analyst_data_path = analyst_data_path.strip()

        def _read_json(path: str):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        data = await asyncio.to_thread(_read_json, analyst_data_path)
        
        if "error" in data:
            logging.error(f"[RESEARCHER] ❌ Analyst data contains errors, cannot conduct research: {data.get('error')}")
            return json.dumps({"error": "Analyst data contains errors, cannot conduct research", "details": data.get("error")}, ensure_ascii=False)
        
        logging.info(f"[RESEARCHER] 🔬 In-depth research: {ticker}")
        logging.debug(f"[RESEARCHER][DEBUG] Analyst data keys: {list(data.keys())}")
        
        # Execute researcher analysis
        result = await research_for_manager(ticker.upper(), data)
        today = datetime.now().strftime("%Y-%m-%d")
        researcher_data_path = f"database/{today}/{ticker}/researcher_{ticker}.json"

        def _write_json(path: str, payload: Dict[str, Any]):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write_json, researcher_data_path, result)
        logging.info(f"[RESEARCHER] 📁 Research report saved to {researcher_data_path}")

        return researcher_data_path
    except json.JSONDecodeError as e:
        logging.error(f"[RESEARCHER] ❌ analyst_data format error, valid JSON required: {str(e)}")
        return json.dumps({
            "error": "analyst_data format error, valid JSON required",
            "details": str(e),
            "received_type": str(type(researcher_data_path))
        }, ensure_ascii=False)
    except Exception as e:
        import traceback
        logging.error(f"[RESEARCHER] ❌ Research analysis failed: {str(e)}")
        return json.dumps({
            "error": f"Research analysis failed: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False)


@tool
def call_trader(ticker: str, research_data_path: str, csv_file_path: str = None, user_request: str = "") -> str:
    """Generate trading decisions based on Researcher report, optionally using Kronos model prediction.
    
    Args:
        ticker: Stock ticker symbol
        research_data_path: JSON data file path returned by call_researcher (must call call_researcher first)
        csv_file_path: Optional, CSV file path (for Kronos prediction, from analyst's market data)
        user_request: User's original request, used to determine if Kronos prediction is needed
    
    Returns:
        Trading decision card in JSON format
    """
    try:
        research_data_path = research_data_path.strip()
        with open(research_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "error" in data:
            return json.dumps({"error": "Research data contains errors, cannot generate trading decision", "details": data.get("error")}, ensure_ascii=False)
        
        logging.info("[TRADER] 💹 Generating trading decision")
        logging.debug(f"[TRADER][DEBUG] Research data keys: {list(data.keys())}")
        
        # Save researcher data directly (Trader will handle format conversion)
        import time
        workspace_dir = os.path.dirname(os.path.dirname(__file__))
        temp_dir = os.path.join(workspace_dir, '.temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = int(time.time() * 1000)
        temp_research_file = os.path.join(temp_dir, f'research_{timestamp}.json')
        
        with open(temp_research_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logging.debug(f"[TRADER][DEBUG] Saved research data to: {temp_research_file}")
        
        try:
            # Initialize trader and generate decision
            trader = Trader()
            csv_files = [csv_file_path] if csv_file_path else None
            request_started = datetime.utcnow()
            
            # Build complete request including user request
            trader_request = f"Please generate trading decision card based on research conclusions. Research file: {temp_research_file}"
            if user_request:
                trader_request += f"\nUser's original request: {user_request}"
            if csv_files:
                trader_request += f"\nCSV files: {', '.join(csv_files)}"
            
            result = trader.process_request(trader_request, temp_research_file, csv_files)
            today = datetime.now().strftime("%Y-%m-%d")
            trader_data_path = f"database/{today}/{ticker}/trader_{ticker}.json"
            with open(trader_data_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logging.info(f"[TRADER] 📁 Trading decision saved to {trader_data_path}")

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
                logging.warning(f"[RISK] ⚠️ Automatic risk management failed: {risk_exc}")
                risk_meta = {"risk_error": str(risk_exc)}
                trader_excerpt = trader_notes
                human_readout = (
                    f"{ticker.upper()} Risk module temporarily unavailable, proceed with caution. "
                    f"Trading recommendation summary: {trader_excerpt[:200]}..."
                )
                risk_meta.setdefault("warning", "Automatic risk control failed, for reference only")

            if not human_readout:
                human_readout = f"{ticker.upper()} Trading recommendation summary: {trader_notes[:200]}..."

            kronos_assets = _find_recent_kronos_assets(ticker, since=request_started)
            if kronos_assets:
                chart_caption = f"{ticker.upper()} Kronos Prediction"
                metadata_url = kronos_assets.get("metadata_url")
                history_url = kronos_assets.get("input_csv_url")
                prediction_url = kronos_assets.get("csv_url")
                if metadata_url or prediction_url:
                    placeholder_parts = [
                        f'symbol="{ticker.upper()}"'
                    ]
                    if metadata_url:
                        placeholder_parts.append(f'metadata="{metadata_url}"')
                    if history_url:
                        placeholder_parts.append(f'history="{history_url}"')
                    if prediction_url:
                        placeholder_parts.append(f'prediction="{prediction_url}"')
                    placeholder = "<kronos-chart " + " ".join(placeholder_parts) + " />"
                    human_readout += f"\n\n{chart_caption}\n{placeholder}"
                elif kronos_assets.get("plot_url"):
                    human_readout += f"\n\n![{chart_caption}]({kronos_assets['plot_url']})"

            response_payload: Dict[str, Any] = {
                "status": "success",
                "trader_notes": trader_notes,
                "human_readout": human_readout,
            }
            if kronos_assets:
                response_payload["kronos_assets"] = kronos_assets
            response_payload.update(risk_meta)
            return json.dumps(response_payload, ensure_ascii=False)
        finally:
            # Always cleanup temp file
            try:
                if os.path.exists(temp_research_file):
                    os.unlink(temp_research_file)
                    logging.debug(f"[TRADER][DEBUG] Cleaned up: {temp_research_file}")
            except Exception as e:
                logging.debug(f"[TRADER][DEBUG] Cleanup warning: {e}")
    except json.JSONDecodeError as e:
        return json.dumps({
            "error": "research_data format error, valid JSON required",
            "details": str(e),
            "received_type": str(type(research_data_path))
        }, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps({
            "error": f"Trading decision generation failed: {str(e)}",
            "traceback": traceback.format_exc()
        }, ensure_ascii=False)

########################################
#        Main Agent Configuration      #
########################################

def build_main_agent(config=None, memory: ToolAwareConversationMemory | None = None):
    """Create an AgentExecutor with LangChain native memory."""
    tools = [read_file, write_file, call_analyst, call_researcher, call_trader, call_risk_manager]
    
    # Dynamic configuration description
    if config:
        enabled_types = [k for k, v in config.items() if v]
        analysis_desc = f"Currently enabled: {', '.join(enabled_types)}" if enabled_types else "All analysis types disabled"
    else:
        analysis_desc = "All analysis types enabled"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are the Market Lens AI main agent, a professional, intelligent, and autonomous financial market analysis assistant.\n\n"
         "🎯 Core Mission: Quickly understand user intent, rationally coordinate tool chains, and generate actionable market insights and trading recommendations.\n\n"
         "📋 Available Tools:\n"
         "1. call_analyst: Collect stock raw data (news / fundamentals / market / sentiment).\n"
         "2. call_researcher: Conduct in-depth research based on data (bull/bear debate, investment recommendations).\n"
         "3. call_trader: Generate trading decisions, supports user_request parameter to pass user needs.\n"
         "4. call_risk_manager: Review or supplement risk conclusions when necessary.\n"
         "5. read_file / write_file: Manage and track historical files, notes, and intermediate results.\n\n"
         "🧠 Autonomous Management:\n"
         "- Before each response, determine if existing conversation and saved files can directly meet needs; first retrieve relevant summaries or historical results via read_file.\n"
         "- When obtaining new conclusions, key parameters, or action items, use write_file to save concise notes for future reference; confirm before writing to avoid overwriting content that needs to be retained.\n"
         "- Avoid repeatedly running expensive tools. Unless needs change or historical files are missing/outdated, prioritize reusing existing results and explain the basis for reuse in the response.\n"
         "- Tool calls must align with user goals: collect data when lacking, research deeply when logic exists, execute when strategy is present, and verify when risks exist.\n\n"
         "🔄 Recommended Workflow:\n"
         "- Complete research: call_analyst → call_researcher → call_trader → (if necessary) call_risk_manager.\n"
         "- In-depth research: call_analyst → call_researcher.\n"
         "- Quick query or reuse history: read_file to retrieve notes → call relevant tools if updates needed.\n\n"
         "⚠️ Response Requirements:\n"
         "- Do not reveal any actual file paths or internal storage locations in user responses.\n"
         "- When tools return human_readout, make it the core of the response and supplement with necessary context.\n"
         "- Output must be specific: include direction, position, stop-loss/take-profit, trigger conditions and other key values; explain gaps if data is insufficient.\n"
         "- When risk control fails, remind users to proceed with caution and provide current trading points.\n\n"
         f"⚙️ Configuration Status: {analysis_desc}\n\n"
         "📌 Key Notes:\n"
         "- Keep JSON as-is for passthrough, do not arbitrarily modify fields.\n"
         "- When calling call_trader, always write user's original request into user_request parameter.\n"
         "- If user mentions prediction, price outlook, or Kronos, explicitly record in user_request.\n"
         "- When partial analysis fails but usable data exists, continue and inform about missing parts and impact.\n"
         "- Respond to users in English throughout, maintaining a professional, clear, and actionable tone."),
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
        verbose=True,
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
