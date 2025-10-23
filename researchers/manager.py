from typing import Dict, Any
from .adapters import to_research_bundle
from .bullish import bullish_research_tool
from .bearish import bearish_research_tool
from .debate import moderate_debate_tool
import logging

logger = logging.getLogger(__name__)

def validate_analyst_data(analyst_data: Dict[str, Any]) -> Dict[str, bool]:
    """Validate analyst data contains necessary information"""
    analyses = analyst_data.get("analyses", {})
    validation = {}
    
    for channel in ["news", "fundamentals", "sentiment", "market"]:
        channel_data = analyses.get(channel, {})
        has_data = bool(channel_data.get("data"))
        validation[f"{channel}_available"] = has_data
        
    return validation

async def research_for_manager(ticker: str, analyst_data: Dict[str, Any], risk_tolerance: str = "medium", time_horizon: str = "medium", rounds: int = 3) -> Dict[str, Any]:
    """Conduct research analysis on analyst results, generate bull/bear debate and final investment recommendation"""
    logger.info(f"[RESEARCHER] 🔬 Starting research analysis: {ticker} - {rounds} debate rounds")
    # Validate data completeness
    validation = validate_analyst_data(analyst_data)
    logger.debug(f"[RESEARCHER] 📋 Data validation complete: {validation}")
    
    try:
        bundle = to_research_bundle(analyst_data)
    except Exception as e:
        logger.error(f"[RESEARCHER] ❌ Data conversion failed: {ticker} - {e}")
        raise ValueError(f"Data conversion failed: {str(e)}") from e
    
    # Multi-round debate: alternate feeding previous round highlights with history
    debate_history = []
    latest_bull = None
    latest_bear = None
    bull = None
    bear = None

    for i in range(max(1, rounds)):
        logger.info(f"[RESEARCHER] 💬 Debate round {i+1}/{max(1, rounds)} - Bullish turn...")
        try:
            bull = await bullish_research_tool.ainvoke({
                "ticker": ticker,
                "analyst_bundle": bundle,
                "latest_bear": latest_bear,
                "debate_history": debate_history
            })
        except Exception as e:
            logger.error(f"[RESEARCHER] ❌ Bullish research failed: {e}")
            raise ValueError(f"Bullish research failed: {str(e)}") from e

        bull_thesis = (bull or {}).get("thesis") or ""
        bull_args = (bull or {}).get("arguments", [])
        bull_text = (bull_thesis + "\n- " + "\n- ".join(bull_args[:3])).strip()
        debate_history.append({"role": "bullish", "text": bull_text})
        latest_bull = bull_thesis or ("; ".join(bull_args[:2]) if bull_args else None)

        logger.info(f"[RESEARCHER] 💬 Debate round {i+1}/{max(1, rounds)} - Bearish turn...")
        try:
            bear = await bearish_research_tool.ainvoke({
                "ticker": ticker,
                "analyst_bundle": bundle,
                "latest_bull": latest_bull,
                "debate_history": debate_history
            })
        except Exception as e:
            logger.error(f"[RESEARCHER] ❌ Bearish research failed: {e}")
            raise ValueError(f"Bearish research failed: {str(e)}") from e

        bear_thesis = (bear or {}).get("thesis") or ""
        bear_args = (bear or {}).get("arguments", [])
        bear_text = (bear_thesis + "\n- " + "\n- ".join(bear_args[:3])).strip()
        debate_history.append({"role": "bearish", "text": bear_text})
        latest_bear = bear_thesis or ("; ".join(bear_args[:2]) if bear_args else None)
    
    logger.info(f"[RESEARCHER] 🎯 Synthesizing debate results...")
    try:
        decision = await moderate_debate_tool.ainvoke({
            "ticker": ticker,
            "bullish": bull,
            "bearish": bear,
            "risk_tolerance": risk_tolerance,
            "time_horizon": time_horizon
        })
    except Exception as e:
        logger.error(f"[RESEARCHER] ❌ Debate synthesis failed: {e}")
        raise ValueError(f"Debate synthesis failed: {str(e)}") from e
    
    # Extract CSV path (if exists)
    csv_path = analyst_data.get("csv_path")
    
    result = {
        "analyses": analyst_data.get("analyses", {}),
        "bullish_research": bull,
        "bearish_research": bear,
        "final_decision": decision,
        "debate_history": debate_history,
        "rounds": max(1, rounds),
        "ticker": ticker,
        "data_validation": validation,
        "meta": {
            "risk_tolerance": risk_tolerance,
            "time_horizon": time_horizon
        }
    }
    
    # Add CSV path to output if exists
    if csv_path:
        result["csv_path"] = csv_path
    
    logger.info(f"[RESEARCHER] ✅ Research analysis complete: {ticker}")
    return result
