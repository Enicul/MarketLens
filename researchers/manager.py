from typing import Dict, Any
from .adapters import to_research_bundle
from .bullish import bullish_research_tool
from .bearish import bearish_research_tool
from .debate import moderate_debate_tool

def validate_analyst_data(analyst_data: Dict[str, Any]) -> Dict[str, bool]:
    """验证analyst数据是否包含必要信息"""
    analyses = analyst_data.get("analyses", {})
    validation = {}
    
    for channel in ["news", "fundamentals", "sentiment", "market"]:
        channel_data = analyses.get(channel, {})
        has_data = bool(channel_data.get("data"))
        validation[f"{channel}_available"] = has_data
        
    return validation

async def research_for_manager(ticker: str, analyst_data: Dict[str, Any], risk_tolerance: str = "medium", time_horizon: str = "medium", rounds: int = 3) -> Dict[str, Any]:
    """对analyst结果进行研究分析，生成多空辩论和最终投资建议"""
    # 验证数据完整性
    validation = validate_analyst_data(analyst_data)
    
    try:
        bundle = to_research_bundle(analyst_data)
    except Exception as e:
        raise ValueError(f"数据转换失败: {str(e)}") from e
    
    # 多轮辩论：交替喂入上一轮要点与历史
    debate_history = []
    latest_bull = None
    latest_bear = None
    bull = None
    bear = None

    for i in range(max(1, rounds)):
        print(f"[Debate] Round {i+1}/{max(1, rounds)} - Bullish speaking...")
        try:
            bull = await bullish_research_tool.ainvoke({
                "ticker": ticker,
                "analyst_bundle": bundle,
                "latest_bear": latest_bear,
                "debate_history": debate_history
            })
        except Exception as e:
            raise ValueError(f"多头研究失败: {str(e)}") from e

        bull_thesis = (bull or {}).get("thesis") or ""
        bull_args = (bull or {}).get("arguments", [])
        bull_text = (bull_thesis + "\n- " + "\n- ".join(bull_args[:3])).strip()
        debate_history.append({"role": "bullish", "text": bull_text})
        latest_bull = bull_thesis or ("; ".join(bull_args[:2]) if bull_args else None)

        print(f"[Debate] Round {i+1}/{max(1, rounds)} - Bearish responding...")
        try:
            bear = await bearish_research_tool.ainvoke({
                "ticker": ticker,
                "analyst_bundle": bundle,
                "latest_bull": latest_bull,
                "debate_history": debate_history
            })
        except Exception as e:
            raise ValueError(f"空头研究失败: {str(e)}") from e

        bear_thesis = (bear or {}).get("thesis") or ""
        bear_args = (bear or {}).get("arguments", [])
        bear_text = (bear_thesis + "\n- " + "\n- ".join(bear_args[:3])).strip()
        debate_history.append({"role": "bearish", "text": bear_text})
        latest_bear = bear_thesis or ("; ".join(bear_args[:2]) if bear_args else None)
    
    try:
        decision = await moderate_debate_tool.ainvoke({
            "ticker": ticker,
            "bullish": bull,
            "bearish": bear,
            "risk_tolerance": risk_tolerance,
            "time_horizon": time_horizon
        })
    except Exception as e:
        raise ValueError(f"辩论综合失败: {str(e)}") from e
    
    return {
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
