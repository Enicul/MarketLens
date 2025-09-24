# trader_agent.py
import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage
from langchain_core.tools import tool

# Add Kronos tools path
current_dir = os.path.dirname(os.path.abspath(__file__))
kronos_tools_path = os.path.join(current_dir, "Kronos", "tools")
sys.path.append(kronos_tools_path)

try:
    from kronos_prediction_tool import KronosPredictionTool
except ImportError:
    print("Warning: Kronos prediction tool not available. Trader will use mock predictions.")
    KronosPredictionTool = None

load_dotenv()

# Import configuration
try:
    from config import get_openai_config, get_trading_config, get_file_paths
    openai_config = get_openai_config()
    trading_config = get_trading_config()
    file_paths = get_file_paths()
    print("✅ Trader configuration loaded successfully")
except ImportError:
    print("⚠️ Configuration file not found, using default settings")
    openai_config = {
        'api_key': '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',
        'model': 'gpt-4o-mini',
        'temperature': 0
    }
    trading_config = {'lookback': 400, 'pred_len': 120}
    file_paths = {'researcher_file': '../researcher.json'}

llm = ChatOpenAI(
    model=openai_config['model'], 
    temperature=openai_config['temperature'],
    api_key=openai_config['api_key']
)

# Initialize Kronos tool globally to avoid repeated initialization
_kronos_tool = None

def get_kronos_tool():
    """Get or initialize the Kronos prediction tool"""
    global _kronos_tool
    if _kronos_tool is None and KronosPredictionTool is not None:
        _kronos_tool = KronosPredictionTool(verbose=False)
        _kronos_tool.initialize()
    return _kronos_tool

@tool
def kronos_stock_prediction(ticker_and_params: str) -> str:
    """
    Use Kronos AI model to predict stock price movements.
    Input should be JSON string with: {"ticker": "AAPL", "lookback": 400, "pred_len": 120, "data_path": "/path/to/csv"}
    
    注意: data_path是可选的，如果analyst没有提供CSV时序数据，会查找默认位置或使用Mock预测
    Returns prediction summary with price change percentage and confidence metrics.
    """
    try:
        params = json.loads(ticker_and_params)
        ticker = params.get("ticker", "UNKNOWN")
        lookback = params.get("lookback", 400)
        pred_len = params.get("pred_len", 120)
        data_path = params.get("data_path")
        
        kronos_tool = get_kronos_tool()
        
        if kronos_tool is None or data_path is None or not os.path.exists(data_path):
            # Mock prediction when Kronos is not available or data is missing
            mock_change = hash(ticker) % 21 - 10  # -10% to +10% based on ticker hash
            return json.dumps({
                "ticker": ticker,
                "prediction_type": "mock",
                "predicted_change_pct": mock_change,
                "confidence": 0.6,
                "prediction_periods": pred_len,
                "signal": "BUY" if mock_change > 2 else "SELL" if mock_change < -2 else "HOLD",
                "summary": f"Mock prediction: {mock_change:+.1f}% price change over {pred_len} periods"
            })
        
        # Real Kronos prediction
        prediction_df = kronos_tool.predict_from_csv(
            csv_path=data_path,
            lookback=lookback,
            pred_len=pred_len
        )
        
        if prediction_df is not None:
            summary = kronos_tool.get_prediction_summary(prediction_df)
            price_stats = summary.get('price_stats', {})
            change_pct = price_stats.get('price_change_pct', 0)
            
            # Determine signal based on predicted change
            if change_pct > 3.0:
                signal = "STRONG_BUY"
            elif change_pct > 1.0:
                signal = "BUY"
            elif change_pct < -3.0:
                signal = "STRONG_SELL"
            elif change_pct < -1.0:
                signal = "SELL"
            else:
                signal = "HOLD"
            
            # Calculate confidence based on prediction consistency
            confidence = min(abs(change_pct) / 10.0 + 0.5, 1.0)
            
            return json.dumps({
                "ticker": ticker,
                "prediction_type": "kronos",
                "predicted_change_pct": change_pct,
                "confidence": confidence,
                "prediction_periods": len(prediction_df),
                "signal": signal,
                "price_stats": price_stats,
                "volume_stats": summary.get('volume_stats', {}),
                "summary": f"Kronos AI predicts {change_pct:+.2f}% price change over {pred_len} periods"
            })
        else:
            return json.dumps({
                "ticker": ticker,
                "prediction_type": "error",
                "error": "Kronos prediction failed",
                "summary": "Unable to generate prediction with Kronos model"
            })
            
    except Exception as e:
        return json.dumps({
            "error": f"Kronos prediction tool error: {str(e)}",
            "summary": "Prediction tool encountered an error"
        })

@tool
def generate_trading_decision(analysis_data: str) -> str:
    """
    Generate structured trading decision based on analysis data.
    Input should be JSON string with researcher analysis, optional Kronos prediction, and other data.
    Returns a structured decision card with buy/sell/hold recommendation, position size, risk parameters, and executable proposal.
    """
    try:
        data = json.loads(analysis_data)
        ticker = data.get("ticker", "UNKNOWN")
        
        # Extract researcher analysis (primary source)
        researcher_analysis = data.get("researcher_analysis", {})
        
        # Extract optional Kronos prediction
        kronos_prediction = data.get("kronos_prediction", {})
        
        # Extract legacy analysis data (for backward compatibility)
        market_data = data.get("market", {})
        news_data = data.get("news", {})
        sentiment_data = data.get("sentiment", {})
        fundamentals_data = data.get("fundamentals", {})
        
        # Calculate composite score
        scores = []
        confidence_factors = []
        rationale_parts = []
        
        # Primary: Researcher analysis score (highest weight)
        if researcher_analysis:
            research_signal = researcher_analysis.get("research_signal", "NEUTRAL")
            research_confidence = researcher_analysis.get("research_confidence", 0.5)
            net_score = researcher_analysis.get("net_score", 0.0)
            bull_strength = researcher_analysis.get("bull_strength", 0.5)
            bear_strength = researcher_analysis.get("bear_strength", 0.5)
            
            # Convert research signal to score
            if research_signal == "BULLISH":
                research_score = 0.8 * research_confidence
            elif research_signal == "BEARISH":
                research_score = -0.8 * research_confidence
            else:
                research_score = net_score * research_confidence
            
            scores.append(research_score * 1.5)  # Higher weight for researcher analysis
            confidence_factors.append("researcher_analysis")
            
            # Add key insights to rationale
            key_upside = researcher_analysis.get("key_upside", [])
            key_risks = researcher_analysis.get("key_risks", [])
            if key_upside:
                rationale_parts.append(f"Research upside: {key_upside[0]}")
            if key_risks:
                rationale_parts.append(f"Research risk: {key_risks[0]}")
        
        # Secondary: Kronos AI prediction score
        if kronos_prediction:
            pred_change = kronos_prediction.get("predicted_change_pct", 0)
            pred_confidence = kronos_prediction.get("confidence", 0.5)
            kronos_score = (pred_change / 10.0) * pred_confidence  # Normalize and weight by confidence
            scores.append(kronos_score)
            confidence_factors.append("ai_prediction")
            rationale_parts.append(f"AI predicts {pred_change:+.1f}% change")
        
        # Legacy analysis scores (lower weight for backward compatibility)
        # Market technical score
        if market_data:
            market_summary = market_data.get("summary", "").lower()
            if "bullish" in market_summary or "uptrend" in market_summary:
                scores.append(0.4)  # Reduced weight
            elif "bearish" in market_summary or "downtrend" in market_summary:
                scores.append(-0.4)
            else:
                scores.append(0.1)
            confidence_factors.append("technical_analysis")
        
        # News sentiment score
        if news_data:
            news_summary = news_data.get("summary", "").lower()
            if "positive" in news_summary or "beat" in news_summary or "growth" in news_summary:
                scores.append(0.3)  # Reduced weight
            elif "negative" in news_summary or "miss" in news_summary or "decline" in news_summary:
                scores.append(-0.3)
            else:
                scores.append(0.0)
            confidence_factors.append("news_sentiment")
        
        # Social sentiment score
        if sentiment_data:
            sentiment_summary = sentiment_data.get("summary", "").lower()
            if "bullish" in sentiment_summary or "optimistic" in sentiment_summary:
                scores.append(0.2)  # Reduced weight
            elif "bearish" in sentiment_summary or "pessimistic" in sentiment_summary:
                scores.append(-0.2)
            else:
                scores.append(0.0)
            confidence_factors.append("social_sentiment")
        
        # Fundamentals score
        if fundamentals_data:
            fund_summary = fundamentals_data.get("summary", "").lower()
            if "strong" in fund_summary or "healthy" in fund_summary or "profitable" in fund_summary:
                scores.append(0.2)  # Reduced weight
            elif "weak" in fund_summary or "struggling" in fund_summary or "loss" in fund_summary:
                scores.append(-0.2)
            else:
                scores.append(0.0)
            confidence_factors.append("fundamentals")
        
        # Calculate final score and decision
        if scores:
            final_score = sum(scores) / len(scores)
            base_confidence = len(confidence_factors) / 5.0  # Max 5 factors
            
            # Determine action
            if final_score > 0.3:
                action = "BUY"
                position_size = min(0.15 + (final_score - 0.3) * 0.2, 0.25)  # 15-25%
            elif final_score < -0.3:
                action = "SELL"
                position_size = min(0.10 + abs(final_score + 0.3) * 0.15, 0.20)  # 10-20%
            else:
                action = "HOLD"
                position_size = 0.05  # Small position for unclear signals
            
            # Risk parameters
            stop_loss_pct = 0.08 if action == "BUY" else 0.06 if action == "SELL" else 0.05
            take_profit_pct = 0.12 if action == "BUY" else 0.10 if action == "SELL" else 0.08
            
            # Confidence calculation
            confidence = min(base_confidence + abs(final_score) * 0.3, 1.0)
            
            # Time horizon based on signal strength
            if abs(final_score) > 0.6:
                horizon = "3-7 trading days"
            elif abs(final_score) > 0.4:
                horizon = "5-10 trading days"
            else:
                horizon = "7-15 trading days"
            
            # Generate comprehensive rationale
            rationale = rationale_parts.copy()  # Start with parts from analysis
            
            # Add additional rationale based on decision strength
            if len(confidence_factors) >= 3:
                rationale.append("Multi-source analysis convergence")
            if abs(final_score) > 0.5:
                rationale.append("Strong signal across indicators")
            
            # Add researcher-specific insights
            if researcher_analysis:
                research_rec = researcher_analysis.get("recommendation", "")
                if research_rec and research_rec != action:
                    rationale.append(f"Research suggests {research_rec}, adjusted for market conditions")
                
                uncertainty = researcher_analysis.get("uncertainty", 0)
                if uncertainty > 0.4:
                    rationale.append("High research uncertainty considered")
            
            # Determine time horizon based on researcher input or default logic
            if researcher_analysis:
                research_horizon = researcher_analysis.get("time_horizon", "medium")
                if research_horizon == "short":
                    horizon = "1-5 trading days"
                elif research_horizon == "long":
                    horizon = "15-30 trading days"
                else:  # medium
                    if abs(final_score) > 0.6:
                        horizon = "5-10 trading days"
                    else:
                        horizon = "7-15 trading days"
            else:
                # Default horizon logic
                if abs(final_score) > 0.6:
                    horizon = "3-7 trading days"
                elif abs(final_score) > 0.4:
                    horizon = "5-10 trading days"
                else:
                    horizon = "7-15 trading days"
            
            decision_card = {
                "ticker": ticker,
                "signal": action,
                "size_pct": round(position_size, 3),
                "confidence": round(confidence, 2),
                "composite_score": round(final_score, 3),
                "horizon": horizon,
                "risk": {
                    "stop_loss_pct": stop_loss_pct,
                    "take_profit_pct": take_profit_pct,
                    "max_drawdown_pct": stop_loss_pct * 1.5
                },
                "rationale": rationale[:5],  # Limit to top 5 rationale points
                "evidence_sources": confidence_factors,
                "analysis_timestamp": "2025-09-23T00:00:00Z",
                "researcher_summary": {
                    "recommendation": researcher_analysis.get("recommendation", "N/A") if researcher_analysis else "N/A",
                    "confidence": researcher_analysis.get("rec_confidence", 0) if researcher_analysis else 0,
                    "net_score": researcher_analysis.get("net_score", 0) if researcher_analysis else 0,
                    "uncertainty": researcher_analysis.get("uncertainty", 0) if researcher_analysis else 0
                },
                "kronos_used": bool(kronos_prediction),
                "proposal": ""  # Will be filled by generate_executable_proposal
            }
            
            return json.dumps(decision_card, indent=2)
        
        else:
            # No data available
            return json.dumps({
                "ticker": ticker,
                "signal": "HOLD",
                "size_pct": 0.0,
                "confidence": 0.0,
                "error": "Insufficient analysis data",
                "rationale": ["No sufficient data for decision making"]
            })
            
    except Exception as e:
        return json.dumps({
            "error": f"Decision generation error: {str(e)}",
            "signal": "HOLD",
            "confidence": 0.0
        })

# Note: Agent creation moved to after tool definitions

# Helper function to read researcher output
def read_researcher_output(researcher_file_path: str = "researcher.json") -> dict:
    """
    Read researcher output from JSON file
    
    Args:
        researcher_file_path: Path to researcher output file
        
    Returns:
        dict: Researcher analysis data
    """
    try:
        # Use configured path if available
        if 'file_paths' in globals() and researcher_file_path == "researcher.json":
            full_path = file_paths.get('researcher_file', researcher_file_path)
        else:
            # Fallback to relative path
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            full_path = os.path.join(project_root, researcher_file_path)
        
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"Warning: Researcher file not found at {full_path}")
            return {}
    except Exception as e:
        print(f"Error reading researcher output: {e}")
        return {}

@tool
def analyze_researcher_output(researcher_data: str) -> str:
    """
    Analyze researcher output and extract key trading signals.
    Input should be JSON string with researcher analysis data.
    Returns structured analysis of research findings for trading decisions.
    """
    try:
        data = json.loads(researcher_data)
        ticker = data.get("ticker", "UNKNOWN")
        
        # Extract key components
        stance_summary = data.get("stance_summary", {})
        consensus = data.get("consensus", [])
        disagreements = data.get("disagreements", [])
        key_upside = data.get("key_upside", [])
        key_risks = data.get("key_risks", [])
        scorecard = data.get("scorecard", {})
        action = data.get("action", {})
        rationale = data.get("rationale", "")
        
        # Calculate research signal strength
        bull_strength = scorecard.get("bull_strength", 0.5)
        bear_strength = scorecard.get("bear_strength", 0.5)
        uncertainty = scorecard.get("uncertainty", 0.5)
        net_score = scorecard.get("net_score", 0.0)
        
        # Determine research signal
        if net_score > 0.2:
            research_signal = "BULLISH"
        elif net_score < -0.2:
            research_signal = "BEARISH"
        else:
            research_signal = "NEUTRAL"
        
        # Calculate confidence based on uncertainty
        research_confidence = max(0.1, 1.0 - uncertainty)
        
        # Extract recommendation
        recommendation = action.get("recommendation", "HOLD")
        rec_confidence = action.get("confidence", 0.5)
        time_horizon = action.get("time_horizon", "medium")
        
        # Count positive vs negative factors
        upside_count = len(key_upside)
        risk_count = len(key_risks)
        disagreement_count = len(disagreements)
        
        analysis_result = {
            "ticker": ticker,
            "research_signal": research_signal,
            "research_confidence": research_confidence,
            "net_score": net_score,
            "recommendation": recommendation,
            "rec_confidence": rec_confidence,
            "time_horizon": time_horizon,
            "bull_strength": bull_strength,
            "bear_strength": bear_strength,
            "uncertainty": uncertainty,
            "upside_factors": upside_count,
            "risk_factors": risk_count,
            "disagreements": disagreement_count,
            "consensus_points": len(consensus),
            "key_upside": key_upside[:3],  # Top 3 upside factors
            "key_risks": key_risks[:3],   # Top 3 risk factors
            "rationale": rationale,
            "bullish_thesis": stance_summary.get("bullish_thesis", ""),
            "bearish_thesis": stance_summary.get("bearish_thesis", ""),
            "triggers_up": action.get("triggers_up", []),
            "triggers_down": action.get("triggers_down", [])
        }
        
        return json.dumps(analysis_result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"Researcher analysis error: {str(e)}",
            "ticker": "UNKNOWN",
            "research_signal": "NEUTRAL",
            "research_confidence": 0.0
        })

@tool
def should_use_kronos_prediction(analysis_summary: str) -> str:
    """
    Determine if Kronos AI prediction should be used based on analysis context.
    Input should be JSON string with analysis summary.
    Returns recommendation on whether to use Kronos prediction.
    """
    try:
        data = json.loads(analysis_summary)
        
        # Factors that favor using Kronos
        use_kronos_factors = []
        
        # 1. High uncertainty suggests need for AI prediction
        uncertainty = data.get("uncertainty", 0.5)
        if uncertainty > 0.4:
            use_kronos_factors.append("high_uncertainty")
        
        # 2. Conflicting signals suggest need for additional analysis
        disagreement_count = data.get("disagreements", 0)
        if disagreement_count > 2:
            use_kronos_factors.append("conflicting_signals")
        
        # 3. Neutral research signal suggests need for technical prediction
        research_signal = data.get("research_signal", "NEUTRAL")
        if research_signal == "NEUTRAL":
            use_kronos_factors.append("neutral_research")
        
        # 4. Medium/long time horizon benefits from price prediction
        time_horizon = data.get("time_horizon", "medium")
        if time_horizon in ["medium", "long"]:
            use_kronos_factors.append("suitable_horizon")
        
        # 5. Low research confidence suggests need for additional input
        research_confidence = data.get("research_confidence", 0.5)
        if research_confidence < 0.6:
            use_kronos_factors.append("low_confidence")
        
        # Decision logic
        use_kronos = len(use_kronos_factors) >= 2
        confidence = len(use_kronos_factors) / 5.0  # Normalize to 0-1
        
        result = {
            "use_kronos": use_kronos,
            "confidence": confidence,
            "reasons": use_kronos_factors,
            "rationale": f"{'Recommend' if use_kronos else 'Skip'} Kronos prediction based on {len(use_kronos_factors)} factors"
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "use_kronos": True,  # Default to using Kronos on error
            "confidence": 0.5,
            "reasons": ["error_fallback"],
            "error": str(e)
        })

# Helper function for Manager to call
async def trade_for_manager(ticker: str, analysis_data: dict = None, use_kronos: bool = True, researcher_file: str = "researcher.json", csv_data_path: str = "") -> dict:
    """
    Generate trading decision based on researcher output and optional Kronos AI prediction.
    
    Args:
        ticker: Stock symbol
        analysis_data: Dict containing analysis from different teams (optional, for backward compatibility)
        use_kronos: Whether to consider using Kronos AI prediction
        researcher_file: Path to researcher output JSON file
        csv_data_path: Path to CSV time series data file for Kronos prediction
    
    Returns:
        dict: Structured trading decision card with executable trading proposal
    """
    try:
        # Step 1: Read researcher output
        researcher_data = read_researcher_output(researcher_file)
        
        if not researcher_data:
            return {
                "ticker": ticker,
                "signal": "HOLD",
                "confidence": 0.0,
                "error": "No researcher data available",
                "proposal": "Cannot generate trading proposal without research data"
            }
        
        # Prepare comprehensive input for trader agent
        user_input_parts = [
            f"Ticker: {ticker}",
            f"Researcher Data: {json.dumps(researcher_data)}"
        ]
        
        # Add legacy analysis data if provided (for backward compatibility)
        if analysis_data:
            user_input_parts.append(f"Additional Analysis: {json.dumps(analysis_data)}")
        
        # Add CSV data path information if provided
        if csv_data_path:
            user_input_parts.append(f"CSV Data Path: {csv_data_path}")
        
        # Add task description
        if use_kronos:
            task_description = (
                "Task: Analyze the researcher output, determine if Kronos AI prediction is needed, "
                "and generate a comprehensive trading decision with executable trading proposal. "
                f"{'Use the provided CSV data path for Kronos prediction if available.' if csv_data_path else ''}"
                "Follow this workflow:\n"
                "1. Analyze the researcher output to extract key trading signals\n"
                "2. Determine if Kronos AI prediction would be beneficial\n"
                "3. If recommended, use Kronos prediction with available time series data\n"
                "4. Generate final trading decision card with executable proposal"
            )
        else:
            task_description = (
                "Task: Analyze the researcher output and generate a trading decision "
                "with executable trading proposal based solely on research findings."
            )
        
        user_input_parts.append(task_description)
        user_input = "\n\n".join(user_input_parts)
        
        # Execute trader agent
        resp = await executor.ainvoke({"input": user_input, "history": []})
        output = resp["output"]
        
        try:
            # Try to parse as JSON
            result = json.loads(output)
            
            # Ensure we have an executable trading proposal
            if "proposal" not in result or not result["proposal"]:
                result["proposal"] = generate_executable_proposal(result)
            
            return result
        except json.JSONDecodeError as e:
            # If output is not valid JSON, try to extract JSON from the output
            print(f"JSON parsing error: {e}")
            print(f"Raw output: {output}")
            
            # Try to find JSON in the output
            import re
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    if "proposal" not in result or not result["proposal"]:
                        result["proposal"] = generate_executable_proposal(result)
                    return result
                except:
                    pass
            
            # If all parsing fails, return error
            basic_result = {
                "ticker": ticker,
                "signal": "HOLD",
                "confidence": 0.0,
                "error": "Invalid trader output format",
                "raw_output": output,
                "proposal": f"Hold position in {ticker} due to analysis error"
            }
            return basic_result
            
    except Exception as e:
        return {
            "ticker": ticker,
            "signal": "HOLD", 
            "confidence": 0.0,
            "error": f"Trader execution error: {str(e)}",
            "proposal": f"Hold position in {ticker} due to system error"
        }

def generate_executable_proposal(decision_card: dict) -> str:
    """
    Generate executable trading proposal based on decision card
    
    Args:
        decision_card: Trading decision card
        
    Returns:
        str: Executable trading proposal
    """
    ticker = decision_card.get("ticker", "STOCK")
    signal = decision_card.get("signal", "HOLD")
    size_pct = decision_card.get("size_pct", 0.0)
    confidence = decision_card.get("confidence", 0.0)
    
    risk_params = decision_card.get("risk", {})
    stop_loss = risk_params.get("stop_loss_pct", 0.05)
    take_profit = risk_params.get("take_profit_pct", 0.10)
    
    horizon = decision_card.get("horizon", "medium-term")
    rationale = decision_card.get("rationale", [])
    
    if signal == "BUY":
        proposal = f"""
EXECUTABLE TRADING PROPOSAL - BUY {ticker}

Position: Open LONG position in {ticker}
Size: {size_pct*100:.1f}% of portfolio
Confidence: {confidence*100:.1f}%
Time Horizon: {horizon}

Execution Plan:
1. Market/Limit Order: Buy {ticker} shares worth {size_pct*100:.1f}% of portfolio value
2. Set Stop Loss: {stop_loss*100:.1f}% below entry price
3. Set Take Profit: {take_profit*100:.1f}% above entry price
4. Review Position: Monitor for {horizon}

Risk Management:
- Maximum loss per trade: {stop_loss*100:.1f}%
- Target profit: {take_profit*100:.1f}%
- Position size limit: {size_pct*100:.1f}% of portfolio

Rationale: {' | '.join(rationale) if rationale else 'Based on comprehensive analysis'}
        """.strip()
    
    elif signal == "SELL":
        proposal = f"""
EXECUTABLE TRADING PROPOSAL - SELL {ticker}

Position: Open SHORT position or Reduce LONG exposure in {ticker}
Size: {size_pct*100:.1f}% of portfolio
Confidence: {confidence*100:.1f}%
Time Horizon: {horizon}

Execution Plan:
1. If holding LONG: Reduce position by {size_pct*100:.1f}% of portfolio value
2. If no position: Consider short position (if available and suitable)
3. Set Stop Loss: {stop_loss*100:.1f}% above entry price (for short)
4. Set Take Profit: {take_profit*100:.1f}% below entry price (for short)

Risk Management:
- Maximum loss per trade: {stop_loss*100:.1f}%
- Target profit: {take_profit*100:.1f}%
- Position adjustment: {size_pct*100:.1f}% of portfolio

Rationale: {' | '.join(rationale) if rationale else 'Based on comprehensive analysis'}
        """.strip()
    
    else:  # HOLD
        proposal = f"""
EXECUTABLE TRADING PROPOSAL - HOLD {ticker}

Position: Maintain current position in {ticker}
Action: No immediate trading action required
Confidence: {confidence*100:.1f}%
Time Horizon: {horizon}

Monitoring Plan:
1. Continue monitoring {ticker} for signal changes
2. Review position allocation if currently holding
3. Watch for trigger events that may change outlook
4. Reassess in next trading cycle

Current Assessment:
- No strong directional bias identified
- Risk/reward not favorable for new positions
- Market conditions suggest patience

Rationale: {' | '.join(rationale) if rationale else 'Neutral outlook based on analysis'}
        """.strip()
    
    return proposal

########################################
#         Agent Creation               #
########################################

# Trader Agent Prompt
prompt = ChatPromptTemplate.from_messages([
    SystemMessage(
        content=(
            "You are the Trader Agent, a sophisticated Wall Street trading professional.\n"
            "You receive researcher output and generate executable trading decisions with detailed proposals.\n\n"
            "Your capabilities:\n"
            "1) analyze_researcher_output - Extract key trading signals from research reports\n"
            "2) should_use_kronos_prediction - Intelligently determine when AI prediction adds value\n"
            "3) kronos_stock_prediction - Advanced AI model for price prediction (when beneficial)\n"
            "4) generate_trading_decision - Create structured decision cards with executable proposals\n\n"
            "Your workflow:\n"
            "1. ANALYZE RESEARCH: Use analyze_researcher_output to extract trading signals from researcher data\n"
            "2. EVALUATE AI NEED: Use should_use_kronos_prediction to determine if Kronos adds value\n"
            "3. GET AI PREDICTION: If recommended, use kronos_stock_prediction for price forecasts\n"
            "4. GENERATE DECISION: Use generate_trading_decision to create final trading recommendation\n\n"
            "Key considerations:\n"
            "- Researcher output contains bullish/bearish thesis, consensus, disagreements, and scorecard\n"
            "- High uncertainty or neutral research signals may benefit from Kronos prediction\n"
            "- Balance research insights with technical AI predictions when both available\n"
            "- Generate executable trading proposals with specific position sizes and risk parameters\n\n"
            "Decision Card Format (must include):\n"
            "- ticker: Stock symbol\n"
            "- signal: BUY/SELL/HOLD\n"
            "- size_pct: Position size as portfolio percentage\n"
            "- confidence: Decision confidence (0.0-1.0)\n"
            "- horizon: Expected holding period\n"
            "- risk: Stop loss, take profit, max drawdown parameters\n"
            "- rationale: Key reasons supporting the decision\n"
            "- proposal: Detailed executable trading proposal text\n\n"
            "OUTPUT FORMAT: Return JSON ONLY with the complete decision card including proposal."
        )
    ),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# Create Trader Agent
agent = create_openai_functions_agent(
    llm=llm,
    tools=[analyze_researcher_output, should_use_kronos_prediction, kronos_stock_prediction, generate_trading_decision],
    prompt=prompt,
)

executor = AgentExecutor(
    agent=agent,
    tools=[analyze_researcher_output, should_use_kronos_prediction, kronos_stock_prediction, generate_trading_decision],
    verbose=True,
    handle_parsing_errors=True,
)

########################################
#            Demo Function             #
########################################

# Demo function
async def main():
    """Demo the trader agent with researcher integration"""
    print("=== Trader Agent Demo with Researcher Integration ===")
    
    # Test 1: Using researcher.json file
    print("\n1. Testing with researcher.json file...")
    result = await trade_for_manager("AAPL", use_kronos=True, researcher_file="researcher.json")
    
    print("\n📊 Trading Decision:")
    print(f"Signal: {result.get('signal', 'N/A')}")
    print(f"Confidence: {result.get('confidence', 0)*100:.1f}%")
    print(f"Position Size: {result.get('size_pct', 0)*100:.1f}%")
    
    rationale = result.get('rationale', [])
    if rationale:
        print(f"Rationale: {', '.join(rationale)}")
    
    # Print executable proposal
    proposal = result.get('proposal', 'No proposal generated')
    print(f"\n📋 Executable Trading Proposal:\n{proposal}")
    
    # Test 2: Direct researcher data test
    print(f"\n{'='*60}")
    print("2. Testing direct researcher data processing...")
    
    researcher_data = read_researcher_output("researcher.json")
    if researcher_data:
        ticker = researcher_data.get('ticker', 'UNKNOWN')
        recommendation = researcher_data.get('action', {}).get('recommendation', 'N/A')
        confidence = researcher_data.get('action', {}).get('confidence', 0)
        net_score = researcher_data.get('scorecard', {}).get('net_score', 0)
        
        print(f"Researcher Analysis for {ticker}:")
        print(f"- Recommendation: {recommendation}")
        print(f"- Confidence: {confidence*100:.1f}%")
        print(f"- Net Score: {net_score:.3f}")
        print(f"- Bull Strength: {researcher_data.get('scorecard', {}).get('bull_strength', 0):.1f}")
        print(f"- Bear Strength: {researcher_data.get('scorecard', {}).get('bear_strength', 0):.1f}")
        print(f"- Uncertainty: {researcher_data.get('scorecard', {}).get('uncertainty', 0):.1f}")
    else:
        print("❌ Could not read researcher data")
    
    print(f"\n{'='*60}")
    print("✅ Demo completed!")

if __name__ == "__main__":
    asyncio.run(main())
