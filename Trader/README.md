# Trader 子Agent - 基于LangChain的智能交易系统

## 🚀 核心特性

- **LangChain架构**: 使用LangChain工具装饰器，与主Agent保持一致
- **智能决策**: GPT-4o-mini作为决策大脑，自动选择合适的工具
- **模块化设计**: 每个功能都是独立的@tool装饰器函数
- **主Agent接口**: 提供标准化接口供主Agent调用

## 快速开始

### 1. 安装依赖

```bash
pip install pandas numpy langchain langchain-openai langchain-core matplotlib
```

### 2. 基本使用

```python
from trader import Trader

# 初始化Trader Agent
trader = Trader()

# 方式1: 主Agent调用接口
result = trader.analyze_and_decide(
    research_json="research_conclusion.json",
    csv_files=["AAPL_data.csv", "TSLA_data.csv"]
)

# 方式2: 自然语言请求
result = trader.process_request(
    "请分析研究结论，如果不确定性高就用Kronos预测，生成决策卡",
    research_json="research_conclusion.json",
    csv_files=["AAPL_data.csv"]
)

# 查看结果（LangChain返回字符串结果）
print("交易决策结果:", result)

# 查看可用工具
print("可用工具:", trader.get_available_tools())
```

### 3. 运行示例

```bash
python example.py
```

## 输入格式

### 研究团队结论JSON格式

```json
{
  "date": "2024-01-01",
  "analyst_team": "MarketLens研究团队",
  "market_outlook": "BULLISH",
  "uncertainty_level": "high",
  "use_kronos_prediction": true,
  "key_themes": ["科技股反弹", "AI概念热潮"],
  "symbols": [
    {
      "symbol": "AAPL",
      "current_price": 175.50,
      "recommendation": "BUY",
      "confidence": 0.75,
      "reasoning": "iPhone销售超预期",
      "risk_level": "MEDIUM",
      "time_horizon": "3-6个月"
    }
  ]
}
```

### CSV数据文件（可选，用于Kronos预测）
- 必需列: `open`, `high`, `low`, `close`
- 可选列: `volume`, `amount`, `timestamp`

## 输出格式 - 标准化决策卡

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "research_summary": {
    "analyst_team": "MarketLens研究团队",
    "market_outlook": "BULLISH",
    "uncertainty_level": "high",
    "use_kronos_prediction": true
  },
  "decision_cards": {
    "AAPL": {
      "symbol": "AAPL",
      "decision": "BUY",
      "confidence_score": 0.75,
      "current_price": 175.50,
      "position_sizing": {
        "percentage": 0.075,
        "description": "建议仓位7.5%"
      },
      "execution_range": {
        "min_price": 171.99,
        "max_price": 179.01,
        "description": "在当前价格±2%区间内执行"
      },
      "stop_loss": {
        "price": 166.73,
        "percentage": 0.05,
        "description": "止损价格166.73（5%止损）"
      },
      "take_profit": {
        "price": 201.83,
        "percentage": 0.15,
        "description": "止盈价格201.83（15%止盈）"
      },
      "risk_level": "MEDIUM",
      "time_horizon": "3-6个月",
      "has_prediction": true
    }
  },
  "prediction_data": {
    "AAPL": {
      "predictions": "Kronos预测数据",
      "type": "kronos"
    }
  }
}
```

## 🛠️ LangChain工具

使用`@tool`装饰器定义的工具函数：

```python
@tool
def load_research_data(json_file_path: str) -> str:
    """加载和解析研究团队的分析结论"""

@tool  
def run_kronos_prediction(csv_file_path: str, symbol: str, prediction_length: int = 120) -> str:
    """使用Kronos模型进行股价预测，返回预测图和预测数据"""

@tool
def generate_decision_card(symbol: str, current_price: float, recommendation: str, 
                          confidence: float, reasoning: str, prediction_data: str = None) -> str:
    """生成标准化交易决策卡"""
```

## 🧠 LangChain Agent流程

1. **Agent分析**: 使用`create_tool_calling_agent`创建智能Agent
2. **工具选择**: Agent自动选择需要调用的工具
3. **执行器**: `AgentExecutor`负责工具的执行和结果处理
4. **结果返回**: 返回自然语言格式的分析结果

## 🔗 主Agent集成

```python
# 与主Agent相同的架构模式
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.tools import tool

# 工具定义
@tool
def your_tool(param: str) -> str:
    """工具描述"""
    return "工具结果"

# Agent构建
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
```

## 🎯 Kronos预测工具

Kronos预测功能直接集成在trader.py中，具备以下特性：

- **简洁集成**: 直接在@tool装饰器中实现，无需额外文件
- **图表生成**: 自动生成专业的股价预测图表
- **中文支持**: 解决字体问题，支持中文显示
- **数据返回**: 提供详细的预测数据摘要

### Kronos工具输出

```json
{
  "symbol": "AAPL",
  "plot_path": "prediction_AAPL_20240101_120000.png",
  "prediction_summary": {
    "min_price": 174.20,
    "max_price": 185.60,
    "mean_price": 179.85,
    "prediction_length": 120,
    "price_change": 0.0387
  },
  "success": true
}
```

