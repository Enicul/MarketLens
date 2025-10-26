"""
Trader Sub-Agent - Intelligent Trading Decision System based on LangChain Tool Calling
Uses LLM as the decision brain, intelligently selects and calls trading tools
"""

import os
import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from config import LLM_GOOGLE
import logging

logger = logging.getLogger(__name__)


########################################
#           Trader Tools               #
########################################

def _convert_researcher_to_symbol(ticker, final_decision, analyses):
    """Convert single researcher data to symbol format"""
    # Extract current_price
    current_price = 0.0
    market_data = analyses.get("market", {}).get("data", {})
    if isinstance(market_data, dict):
        stock_info = market_data.get("stock_basic_info", {})
        current_price = stock_info.get("current_price", 0.0)
    
    # Extract uncertainty level from scorecard
    scorecard = final_decision.get("scorecard", {})
    uncertainty_value = scorecard.get("uncertainty", 0.3)
    if uncertainty_value >= 0.6:
        uncertainty_level = "very_high"
    elif uncertainty_value >= 0.4:
        uncertainty_level = "high"
    elif uncertainty_value >= 0.2:
        uncertainty_level = "medium"
    else:
        uncertainty_level = "low"
    
    action = final_decision.get("action", {})
    
    return {
        "symbol": ticker,
        "current_price": current_price,
        "recommendation": action.get("recommendation", "HOLD"),
        "confidence": action.get("confidence", 0.5),
        "rationale": final_decision.get("rationale", ""),
        "uncertainty_level": uncertainty_level,
        "use_kronos_prediction": None,
        "final_decision": {
            "stance_summary": final_decision.get("stance_summary", {}),
            "consensus": final_decision.get("consensus", []),
            "disagreements": final_decision.get("disagreements", []),
            "key_upside": final_decision.get("key_upside", []),
            "key_risks": final_decision.get("key_risks", []),
            "scorecard": scorecard,
            "action": action,
            "triggers_up": action.get("triggers_up", []),
            "triggers_down": action.get("triggers_down", []),
            "evidence_citations": final_decision.get("evidence_citations", [])
        }
    }

@tool
def load_research_data(json_file_path: str) -> str:
    """Load and parse research team's analysis conclusions, supports single and multiple stocks"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Case 1: Single researcher output
        if "final_decision" in data and "ticker" in data:
            symbol = _convert_researcher_to_symbol(
                data.get("ticker", "UNKNOWN"),
                data.get("final_decision", {}),
                data.get("analyses", {})
            )
            # Add CSV path (if exists)
            csv_path = data.get("csv_path")
            if csv_path:
                symbol["csv_path"] = csv_path
                logger.info(f"[TRADER] 📊 CSV file found: {csv_path}")
            converted_data = {"symbols": [symbol]}
            logger.info(f"[TRADER] ✅ Successfully loaded research data: 1 stock (Researcher format)")
            return json.dumps(converted_data, ensure_ascii=False)
        
        # Case 2: Multiple researcher outputs list
        elif isinstance(data, list):
            symbols = []
            for item in data:
                if "final_decision" in item and "ticker" in item:
                    symbol = _convert_researcher_to_symbol(
                        item.get("ticker", "UNKNOWN"),
                        item.get("final_decision", {}),
                        item.get("analyses", {})
                    )
                    # Add CSV path (if exists)
                    csv_path = item.get("csv_path")
                    if csv_path:
                        symbol["csv_path"] = csv_path
                    symbols.append(symbol)
            converted_data = {"symbols": symbols}
            logger.info(f"[TRADER] ✅ Successfully loaded research data: {len(symbols)} stocks (Researcher list format)")
            return json.dumps(converted_data, ensure_ascii=False)
        
        # Case 3: Original symbols format
        else:
            logger.info(f"[TRADER] ✅ Successfully loaded research data: {len(data.get('symbols', []))} stocks")
            return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[TRADER] ❌ Failed to load research data: {e}")
        return json.dumps({"error": f"Failed to load research data: {e}"}, ensure_ascii=False)


@tool
def run_kronos_prediction(csv_file_path: str, symbol: str, prediction_length: int = 120) -> str:
    """Use Kronos model for stock price prediction. Only call when user explicitly requests or research conclusions suggest using prediction."""
    try:
        import sys
        sys.path.append(os.path.join(os.path.dirname(__file__), 'Kronos'))
        from model import Kronos, KronosTokenizer, KronosPredictor
        
        # Load data
        df = pd.read_csv(csv_file_path)
        
        # Normalize column names to the expected schema
        column_mapping = {
            'date': 'timestamp',
            'Date': 'timestamp',
            'open_price': 'open',
            'Open': 'open',
            'high_price': 'high',
            'High': 'high',
            'low_price': 'low',
            'Low': 'low',
            'close_price': 'close',
            'Close': 'close',
            'volume_traded': 'volume',
            'Volume': 'volume'
        }
        df.rename(columns=column_mapping, inplace=True)
        
        # Calculate amount field (if not exists)
        if 'amount' not in df.columns and 'close' in df.columns and 'volume' in df.columns:
            df['amount'] = df['close'] * df['volume']
        
        # Validate required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"CSV file missing columns: {missing_cols}")
        
        # Find timestamp column
        timestamp_col = next((col for col in ['timestamp', 'timestamps', 'datetime'] if col in df.columns), None)
        if not timestamp_col:
            raise ValueError("CSV file missing timestamp column")
        
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        # Initialize the Kronos model stack
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
        predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
        
        # Prepare prediction input using the full CSV feature set
        lookback = min(400, len(df))
        x_df = df.tail(lookback)[required_cols].reset_index(drop=True)
        x_timestamp = df.tail(lookback)[timestamp_col].reset_index(drop=True)
        
        # Generate future timestamps based on the observed interval
        if len(x_timestamp) > 1:
            time_delta = x_timestamp.iloc[-1] - x_timestamp.iloc[-2]
            y_timestamp = pd.date_range(start=x_timestamp.iloc[-1], periods=prediction_length+1, freq=time_delta)[1:]
        else:
            y_timestamp = pd.date_range(start=x_timestamp.iloc[-1], periods=prediction_length+1, freq='5min')[1:]
        
        # Run the Kronos forecast
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=pd.Series(y_timestamp),
            pred_len=prediction_length,
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False
        )
        
        # Create structured output directory
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = os.path.join("database", today, symbol, "Kronos_output")
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 1. Persist prediction CSV (with timestamps)
        pred_df_with_time = pred_df.copy()
        pred_df_with_time.insert(0, 'timestamp', y_timestamp)
        csv_path = os.path.join(output_dir, f"{symbol}_prediction_{timestamp_str}.csv")
        pred_df_with_time.to_csv(csv_path, index=False)
        
        # 2. Produce a professional-looking forecast chart
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle
        
        # Apply capital-markets styling
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # Enforce English-friendly fonts
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        
        fig, ax = plt.subplots(figsize=(14, 8), facecolor='white')
        
        # Prepare time-axis data
        hist_length = min(60, len(df))  # display the most recent 60 observations
        hist_close = df['close'].tail(hist_length)
        hist_timestamps = df[timestamp_col].tail(hist_length)
        pred_close = pred_df['close']
        
        # Convert timestamps
        hist_dates = pd.to_datetime(hist_timestamps)
        pred_dates = pd.to_datetime(y_timestamp)
        
        # Plot historical price (solid navy line)
        ax.plot(hist_dates, hist_close, 
                color='#1f77b4', linewidth=2.5, 
                label=f'Historical Price ({hist_length} days)', alpha=0.9)
        
        # Plot forecast price (red dashed line)
        ax.plot(pred_dates, pred_close, 
                color='#d62728', linewidth=2.5, linestyle='--', 
                label=f'Kronos Prediction ({len(pred_close)} days)', alpha=0.9)
        
        # Shade the predicted range
        pred_min = pred_close.min()
        pred_max = pred_close.max()
        ax.fill_between(pred_dates, pred_min, pred_max, 
                       color='#d62728', alpha=0.1, 
                       label=f'Prediction Range (${pred_min:.2f} - ${pred_max:.2f})')
        
        # Mark the transition between history and forecast
        transition_date = hist_dates.iloc[-1]
        ax.axvline(x=transition_date, color='gray', linestyle=':', alpha=0.7, linewidth=1.5)
        ax.text(transition_date, ax.get_ylim()[1]*0.95, 'Prediction Start', 
                rotation=90, ha='right', va='top', fontsize=10, color='gray')
        
        # Set an informative title and axis labels
        current_price = hist_close.iloc[-1]
        pred_mean = pred_close.mean()
        change_pct = ((pred_mean - current_price) / current_price) * 100
        
        ax.set_title(f'{symbol} Stock Price Prediction Analysis | Kronos AI Model\n'
                    f'Current Price: ${current_price:.2f} → Predicted Avg: ${pred_mean:.2f} '
                    f'({change_pct:+.1f}%)', 
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_ylabel('Stock Price (USD)', fontsize=12, fontweight='bold')
        ax.set_xlabel('Time', fontsize=12, fontweight='bold')
        
        # Tune time-axis formatting
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Configure subtle grid styling
        ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax.set_facecolor('#fafafa')
        
        # Style the legend
        legend = ax.legend(loc='upper left', frameon=True, fancybox=True, shadow=True)
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_alpha(0.9)
        
        # Annotate price statistics
        stats_text = f'''Prediction Statistics:
Min Price: ${pred_close.min():.2f}
Max Price: ${pred_close.max():.2f}
Avg Price: ${pred_close.mean():.2f}
Std Dev: ${pred_close.std():.2f}
Forecast Days: {len(pred_close)}'''
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
                verticalalignment='top', bbox=dict(boxstyle='round', 
                facecolor='white', alpha=0.8), fontsize=10)
        
        # Format Y axis with USD decorations
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.0f}'))
        
        # Final layout adjustments
        plt.tight_layout()
        
        # Persist high-quality image
        plot_path = os.path.join(output_dir, f"{symbol}_prediction_{timestamp_str}.png")
        plt.savefig(plot_path, dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close()
        
        # 3. Store rich metadata payload
        def _relative_to_database(path_str: str) -> str:
            base = Path("database").resolve()
            path = Path(path_str).resolve()
            try:
                return path.relative_to(base).as_posix()
            except ValueError:
                return path.as_posix()

        metadata = {
            "symbol": symbol,
            "prediction_time": datetime.now().isoformat(),
            "input_csv": _relative_to_database(csv_file_path),
            "prediction_length": prediction_length,
            "lookback_length": lookback,
            "prediction_summary": {
                "min_price": float(pred_df['close'].min()),
                "max_price": float(pred_df['close'].max()),
                "mean_price": float(pred_df['close'].mean()),
                "std_price": float(pred_df['close'].std())
            },
            "output_files": {
                "csv": _relative_to_database(csv_path),
                "plot": _relative_to_database(plot_path)
            }
        }

        metadata_path = os.path.join(output_dir, f"{symbol}_metadata_{timestamp_str}.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # Return the complete artifact bundle
        result = {
            "symbol": symbol,
            "output_dir": output_dir,
            "csv_path": csv_path,
            "plot_path": plot_path,
            "metadata_path": metadata_path,
            "prediction_summary": metadata["prediction_summary"]
        }
        
        logger.info(f"[TRADER][KRONOS] ✅ Forecast completed: {symbol}")
        logger.info(f"[TRADER][KRONOS] 📁 Output directory: {output_dir}")
        logger.info(f"[TRADER][KRONOS] 📊 CSV artifact: {os.path.basename(csv_path)}")
        logger.info(f"[TRADER][KRONOS] 📈 Chart: {os.path.basename(plot_path)}")
        logger.info(f"[TRADER][KRONOS] 📝 Metadata: {os.path.basename(metadata_path)}")
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"[TRADER][KRONOS] ❌ Forecast failed for {symbol}: {e}")
        return json.dumps({"error": str(e), "symbol": symbol}, ensure_ascii=False)


@tool
def generate_decision_card(symbol: str, current_price: float, recommendation: str,
                          confidence: float, reasoning: str, prediction_data: Optional[str] = None) -> str:
    """Generate a standardized trading decision card."""
    try:
        # Parse optional prediction payload
        pred_data = None
        if prediction_data:
            try:
                pred_data = json.loads(prediction_data)
            except:
                pass
        
        # Base card skeleton
        card = {
            "symbol": symbol,
            "decision": recommendation.upper(),
            "confidence_score": round(confidence, 3),
            "current_price": current_price,
            "reasoning": reasoning,
            "has_prediction": bool(pred_data),
            "timestamp": datetime.now().isoformat()
        }
        
        # Adjust conviction when forecast data is supplied
        if pred_data and "prediction_summary" in pred_data:
            pred_summary = pred_data["prediction_summary"]
            pred_mean = pred_summary["mean_price"]
            price_change = (pred_mean - current_price) / current_price
            
            # Adjust confidence based on forecast signal
            if abs(price_change) > 0.05:  # forecast shift above 5%
                if (price_change > 0 and recommendation.upper() == "BUY") or (price_change < 0 and recommendation.upper() == "SELL"):
                    confidence = min(0.9, confidence + 0.1)  # nudge confidence upward
                else:
                    confidence = max(0.3, confidence - 0.1)  # guardrail to reduce conviction
            
            card["confidence_score"] = round(confidence, 3)
            card["prediction_insight"] = f"Forecast price change: {price_change:.2%}"

        # Compute risk overlay
        risk_metrics = _calculate_risk_metrics(current_price, recommendation.upper(), confidence)
        card.update(risk_metrics)

        logger.info(f"[TRADER] ✅ Decision card generated for {symbol}: {recommendation}")
        return json.dumps(card, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"[TRADER] ❌ Failed to generate decision card for {symbol}: {e}")
        return json.dumps({"error": f"Failed to generate decision card: {e}", "symbol": symbol}, ensure_ascii=False)


def _calculate_risk_metrics(current_price: float, signal: str, confidence: float) -> Dict:
    """Calculate positioning and guardrails."""
    # Position sizing
    base_position = 0.1 if signal in ['BUY', 'SELL'] else 0
    position_size = base_position * confidence
    position_size = min(position_size, 0.2)  # cap at 20%

    # Stop-loss / take-profit rails
    if signal == "BUY":
        stop_loss = round(current_price * 0.95, 4)
        take_profit = round(current_price * 1.15, 4)
    elif signal == "SELL":
        stop_loss = round(current_price * 1.05, 4)
        take_profit = round(current_price * 0.85, 4)
    else:
        stop_loss = None
        take_profit = None
    
    return {
        "position_size": {
            "percentage": round(position_size, 3),
            "description": f"Suggested allocation {position_size*100:.1f}%"
        },
        "execution_range": {
            "min_price": round(current_price * 0.98, 4),
            "max_price": round(current_price * 1.02, 4),
            "description": "Execute within ±2% of current price"
        },
        "stop_loss": {
            "price": stop_loss,
            "description": f"Stop-loss price {stop_loss}" if stop_loss else "No stop-loss configured"
        },
        "take_profit": {
            "price": take_profit,
            "description": f"Take-profit price {take_profit}" if take_profit else "No take-profit configured"
        }
    }


########################################
#        Trader Agent                  #
########################################

class Trader:
    """Smart trading agent orchestrated via LangChain tool calling."""

    def __init__(self) -> None:
        """Initialize Trader agent."""
        self.llm = LLM_GOOGLE
        self.agent_executor = self._build_agent()
        logger.info("[TRADER] ✅ Trader agent initialized")

    def _build_agent(self) -> AgentExecutor:
        """Construct the trader agent executor."""
        tools = [load_research_data, run_kronos_prediction, generate_decision_card]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are the Market Lens trading officer. Translate research outputs into actionable execution plans.\n"
             "Duties:\n"
             "- Fully digest the research JSON, align with user intent, and craft a coherent strategy.\n"
             "- Maintain a professional, auditable tone; never fabricate missing data—state assumptions explicitly.\n"
             "Available tools:\n"
             "1) load_research_data – load research outputs (including csv_path fields).\n"
             "2) run_kronos_prediction – invoke Kronos when additional forecasting is warranted.\n"
             "3) generate_decision_card – produce a structured trading decision card.\n"
             "Operating guidelines:\n"
             "a. Call load_research_data first and inspect the symbols list.\n"
             "b. Based on user requests, research uncertainty, and csv_path availability, decide whether to run Kronos per symbol; when used, capture prediction_data in the decision card.\n"
             "c. Use generate_decision_card to synthesize research takeaways, risk controls, and sizing, incorporating Kronos insights when provided.\n"
             "Kronos rules of engagement:\n"
             "- Mandatory when the user explicitly asks for forecasts / price outlook / Kronos.\n"
             "- Recommended for “comprehensive analysis” requests or when uncertainty is high / very_high.\n"
             "- When csv_path is available and the user signals interest, run Kronos and reference the key outputs.\n"
             "The final answer must reconcile research, live predictions, and risk controls with clear sourcing."),
            MessagesPlaceholder("chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        
        agent = create_tool_calling_agent(self.llm, tools, prompt)
        
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
        )
    
    def analyze_and_decide(self, research_json: str, csv_files: List[str] = None, use_kronos: bool = None) -> str:
        """Primary agent entrypoint to analyze and generate trading decisions."""
        if use_kronos is False:
            request = f"Generate a trading decision card based on the research conclusions without using Kronos. Research file: {research_json}"
        elif use_kronos is True:
            csv_info = f", CSV files: {', '.join(csv_files)}" if csv_files else ""
            request = f"Generate a trading decision card based on the research conclusions. Kronos forecasting is required. Research file: {research_json}{csv_info}"
        else:
            csv_info = f", CSV files: {', '.join(csv_files)}" if csv_files else ""
            request = f"Generate a trading decision card based on the research conclusions and decide whether Kronos is needed. Research file: {research_json}{csv_info}"
        
        try:
            result = self.agent_executor.invoke({"input": request, "chat_history": []})
            return result["output"]
        except Exception as e:
            return f"❌ Analysis failed: {str(e)}"
    
    def process_request(self, user_request: str, research_json: str = None, csv_files: List[str] = None) -> str:
        """Handle natural-language user requests."""
        context = ""
        if research_json:
            context += f"Research file: {research_json}."
        if csv_files:
            context += f"Available data files: {', '.join(csv_files)}."
        
        full_request = f"{user_request}。{context}"
        
        try:
            result = self.agent_executor.invoke({"input": full_request, "chat_history": []})
            return result["output"]
        except Exception as e:
            return f"❌ Request handling failed: {str(e)}"
    
    def get_available_tools(self) -> List[str]:
        """Return the registered tool list."""
        return [tool.name for tool in self.agent_executor.tools]
