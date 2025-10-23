# Trader Sub-Agent - LangChain-based Intelligent Trading System

## 🚀 Core Features

- **LangChain Architecture**: Uses LangChain tool decorators, consistent with main agent
- **Intelligent Decision Making**: GPT-4o-mini as decision brain, automatically selects appropriate tools
- **Modular Design**: Each function is an independent @tool decorator function
- **Main Agent Interface**: Provides standardized interface for main agent calls

## Quick Start

### 1. Install Dependencies

```bash
pip install pandas numpy langchain langchain-openai langchain-core matplotlib
```

### 2. Basic Usage

```python
from trader import Trader

# Initialize Trader Agent
trader = Trader()

# Method 1: Main agent call interface
result = trader.analyze_and_decide(
    research_json="research_conclusion.json",
    csv_files=["AAPL_data.csv", "TSLA_data.csv"]
)

# Method 2: Natural language request
result = trader.process_request(
    "Please analyze research conclusions, use Kronos prediction if uncertainty is high, generate decision card",
    research_json="research_conclusion.json",
    csv_files=["AAPL_data.csv"]
)

# View result (LangChain returns string result)
print("Trading decision result:", result)

# View available tools
print("Available tools:", trader.get_available_tools())
```

### 3. Run Example

```bash
python example.py
```

## Input Format

### Research Team Conclusion JSON Format

```json
{
  "date": "2024-01-01",
  "analyst_team": "MarketLens Research Team",
  "market_outlook": "BULLISH",
  "uncertainty_level": "high",
  "use_kronos_prediction": true,
  "key_themes": ["Tech stock rebound", "AI concept surge"],
  "symbols": [
    {
      "symbol": "AAPL",
      "current_price": 175.50,
      "recommendation": "BUY",
      "confidence": 0.75,
      "reasoning": "iPhone sales exceed expectations",
      "risk_level": "MEDIUM",
      "time_horizon": "3-6 months"
    }
  ]
}
```

### CSV Data File (Optional, for Kronos prediction)
- Required columns: `open`, `high`, `low`, `close`
- Optional columns: `volume`, `amount`, `timestamp`

## Output Format - Standardized Decision Card

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "research_summary": {
    "analyst_team": "MarketLens Research Team",
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
        "description": "Recommended position 7.5%"
      },
      "execution_range": {
        "min_price": 171.99,
        "max_price": 179.01,
        "description": "Execute within current price ±2% range"
      },
      "stop_loss": {
        "price": 166.73,
        "percentage": 0.05,
        "description": "Stop loss price 166.73 (5% stop loss)"
      },
      "take_profit": {
        "price": 201.83,
        "percentage": 0.15,
        "description": "Take profit price 201.83 (15% take profit)"
      },
      "risk_level": "MEDIUM",
      "time_horizon": "3-6 months",
      "has_prediction": true
    }
  },
  "prediction_data": {
    "AAPL": {
      "predictions": "Kronos prediction data",
      "type": "kronos"
    }
  }
}
```

## 🛠️ LangChain Tools

Tool functions defined with `@tool` decorator:

```python
@tool
def load_research_data(json_file_path: str) -> str:
    """Load and parse research team's analysis conclusions"""

@tool  
def run_kronos_prediction(csv_file_path: str, symbol: str, prediction_length: int = 120) -> str:
    """Use Kronos model for stock price prediction, returns prediction chart and data"""

@tool
def generate_decision_card(symbol: str, current_price: float, recommendation: str, 
                          confidence: float, reasoning: str, prediction_data: str = None) -> str:
    """Generate standardized trading decision card"""
```

## 🧠 LangChain Agent Flow

1. **Agent Analysis**: Create intelligent agent using `create_tool_calling_agent`
2. **Tool Selection**: Agent automatically selects tools to call
3. **Executor**: `AgentExecutor` responsible for tool execution and result handling
4. **Result Return**: Returns analysis result in natural language format

## 🔗 Main Agent Integration

```python
# Same architectural pattern as main agent
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.tools import tool

# Tool definition
@tool
def your_tool(param: str) -> str:
    """Tool description"""
    return "Tool result"

# Agent construction
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)
```

## 🎯 Kronos Prediction Tool

Kronos prediction functionality is directly integrated in trader.py with the following features:

- **Concise Integration**: Implemented directly in @tool decorator, no additional files needed
- **Chart Generation**: Automatically generates professional stock price prediction charts
- **Chinese Support**: Solves font issues, supports Chinese display
- **Data Return**: Provides detailed prediction data summary

### Kronos Tool Output

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
