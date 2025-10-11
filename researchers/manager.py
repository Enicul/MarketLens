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

async def research_for_manager(ticker: str, analyst_data: Dict[str, Any], risk_tolerance: str = "medium", time_horizon: str = "medium") -> Dict[str, Any]:
    """对analyst结果进行研究分析，生成多空辩论和最终投资建议"""
    # 验证数据完整性
    validation = validate_analyst_data(analyst_data)
    
    try:
        bundle = to_research_bundle(analyst_data)
    except Exception as e:
        raise ValueError(f"数据转换失败: {str(e)}") from e
    
    try:
        bull = await bullish_research_tool.ainvoke({"ticker": ticker, "analyst_bundle": bundle})
    except Exception as e:
        raise ValueError(f"多头研究失败: {str(e)}") from e
    
    try:
        bear = await bearish_research_tool.ainvoke({"ticker": ticker, "analyst_bundle": bundle})
    except Exception as e:
        raise ValueError(f"空头研究失败: {str(e)}") from e
    
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
        "ticker": ticker,
        "data_validation": validation,
        "meta": {
            "risk_tolerance": risk_tolerance,
            "time_horizon": time_horizon
        }
    }
