"""
主Agent的Trader相关工具
这些工具可以被主Agent导入和使用，专门处理股票分析和交易决策
"""

import asyncio
import json
import sys
import os
from langchain_core.tools import tool

# Import and setup configuration
try:
    from config import setup_environment
    setup_environment()
    print("✅ Main agent tools configuration loaded")
except ImportError:
    # Fallback configuration
    os.environ['OPENAI_API_KEY'] = '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'
    print("⚠️ Using fallback configuration for main agent tools")

# 添加路径以导入所需模块
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
analysts_path = os.path.join(project_root, "analysts")
sys.path.append(analysts_path)
sys.path.append(current_dir)

# 尝试导入分析和交易模块
MODULES_AVAILABLE = True
try:
    from analyst import analyze_for_manager
    from trader_agent import trade_for_manager
except ImportError:
    print("Warning: Analyst or Trader modules not available. Some features will be limited.")
    MODULES_AVAILABLE = False


@tool  
def generate_trading_decision(trading_params: str) -> str:
    """交易决策工具：基于研究员JSON分析报告和可选的CSV时序数据生成交易决策卡。
    
    必需输入: researcher JSON文件（包含完整的股票分析）
    可选输入: CSV时序数据文件路径（analyst提供，不是每次都有）
    
    输入格式: JSON字符串
    '{"ticker": "AAPL", "researcher_file": "researcher.json", "csv_data_path": "data/AAPL_5min.csv"}'
    
    注意: csv_data_path是可选的，如果没有提供，Trader会查找默认位置或跳过Kronos预测"""
    if not MODULES_AVAILABLE:
        return json.dumps({"error": "交易员模块不可用", "status": "unavailable"}, ensure_ascii=False)
    
    try:
        params = json.loads(trading_params)
        ticker = params.get("ticker", "").upper()
        researcher_file = params.get("researcher_file", "researcher.json")
        csv_data_path = params.get("csv_data_path", "")
        use_kronos = params.get("use_kronos", True)
        
        if not ticker:
            return json.dumps({"error": "股票代码不能为空"}, ensure_ascii=False)
        
        # 运行异步交易决策
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 传递CSV数据路径给trader，让它在需要时用于Kronos预测
            result = loop.run_until_complete(
                trade_for_manager(
                    ticker=ticker, 
                    analysis_data=None,  # 不使用传统分析数据
                    use_kronos=use_kronos, 
                    researcher_file=researcher_file,
                    csv_data_path=csv_data_path
                )
            )
            return json.dumps(result, ensure_ascii=False)
        finally:
            loop.close()
            
    except Exception as e:
        return json.dumps({"error": f"交易决策错误: {str(e)}"}, ensure_ascii=False)


@tool
def researcher_based_trading_decision(trading_input: str) -> str:
    """基于研究员JSON分析报告的交易决策工具。
    
    主要输入: researcher JSON文件（包含完整股票分析）
    可选输入: CSV时序数据文件路径（analyst提供的时序数据，可能没有）
    
    输入格式: 
    - 简单: "AAPL" (使用默认researcher.json)
    - 完整: '{"ticker": "AAPL", "researcher_file": "custom_research.json", "csv_data_path": "data/AAPL_5min.csv"}'
    
    Trader会自动判断是否需要使用Kronos AI预测来增强分析"""
    if not MODULES_AVAILABLE:
        return json.dumps({"error": "交易员模块不可用", "status": "unavailable"}, ensure_ascii=False)
    
    try:
        # 解析输入参数
        if trading_input.startswith('{'):
            # JSON格式输入
            params = json.loads(trading_input)
            ticker = params.get("ticker", "").upper()
            csv_data_path = params.get("csv_data_path", "")
            researcher_file = params.get("researcher_file", "researcher.json")
        else:
            # 简单字符串输入（向后兼容）
            ticker = trading_input.upper().strip()
            csv_data_path = ""
            researcher_file = "researcher.json"
        
        if not ticker:
            return json.dumps({"error": "请提供有效的股票代码"}, ensure_ascii=False)
        
        # 直接使用研究员输出和CSV数据生成交易决策
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            trading_decision = loop.run_until_complete(
                trade_for_manager(
                    ticker=ticker, 
                    analysis_data=None,  # 不使用传统分析数据
                    use_kronos=True,     # 允许智能使用Kronos
                    researcher_file=researcher_file,
                    csv_data_path=csv_data_path
                )
            )
            
            # 添加执行建议
            if trading_decision.get("signal") != "HOLD":
                execution_note = {
                    "execution_priority": "HIGH" if trading_decision.get("confidence", 0) > 0.7 else "MEDIUM",
                    "review_frequency": "DAILY" if trading_decision.get("signal") in ["BUY", "SELL"] else "WEEKLY",
                    "risk_level": "HIGH" if trading_decision.get("size_pct", 0) > 0.15 else "MEDIUM"
                }
                trading_decision["execution_guidance"] = execution_note
            
            return json.dumps(trading_decision, ensure_ascii=False)
            
        finally:
            loop.close()
            
    except Exception as e:
        return json.dumps({"error": f"基于研究员的交易决策错误: {str(e)}"}, ensure_ascii=False)

# 工具列表，供主Agent导入使用
TRADER_TOOLS = [
    generate_trading_decision, 
    researcher_based_trading_decision
]

# 便捷函数：获取所有可用的trader工具
def get_trader_tools():
    """获取所有可用的trader工具"""
    if MODULES_AVAILABLE:
        return TRADER_TOOLS
    else:
        print("Warning: Trader tools not fully available due to missing dependencies")
        return []

# 便捷函数：检查模块可用性
def check_trader_availability():
    """检查trader模块可用性"""
    return MODULES_AVAILABLE

if __name__ == "__main__":
    # 测试工具可用性
    print("🔧 Trader主Agent工具测试")
    print(f"模块可用性: {'✅ 可用' if MODULES_AVAILABLE else '❌ 不可用'}")
    print(f"可用工具数量: {len(get_trader_tools())}")
    
    if MODULES_AVAILABLE:
        print("✅ 所有trader工具已准备就绪，可供主Agent使用")
    else:
        print("⚠️ 部分依赖缺失，请检查模块导入")
