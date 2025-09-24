# Trader Agent 输入输出规范

## 📥 输入规范

### 1. 必需输入：Researcher JSON分析报告

**文件类型**: JSON格式文件  
**内容**: researcher对股票的整体分析  
**默认文件名**: `researcher.json`

**JSON结构示例**:
```json
{
  "ticker": "AAPL",
  "stance_summary": {
    "bullish_thesis": "看涨论点...",
    "bearish_thesis": "看跌论点..."
  },
  "consensus": ["共识要点1", "共识要点2"],
  "disagreements": [
    {
      "topic": "EPS",
      "bull_view": "多头观点",
      "bear_view": "空头观点"
    }
  ],
  "key_upside": ["上涨因素1", "上涨因素2"],
  "key_risks": ["风险因素1", "风险因素2"],
  "scorecard": {
    "bull_strength": 0.7,
    "bear_strength": 0.5,
    "uncertainty": 0.3,
    "net_score": -0.1
  },
  "action": {
    "recommendation": "HOLD",
    "confidence": 0.5,
    "time_horizon": "medium"
  },
  "rationale": "整体分析理由..."
}
```

### 2. 可选输入：CSV时序数据文件路径

**文件类型**: CSV格式文件路径（字符串）  
**来源**: analyst在各个渠道获取的时序数据  
**频率**: 不是每次都有，取决于analyst是否提供

**CSV格式要求**:
```csv
timestamps,open,high,low,close,volume,amount
2024-01-01 09:30:00,150.0,152.0,149.5,151.0,1000000,151000000
2024-01-01 09:35:00,151.0,153.0,150.5,152.5,1200000,182400000
...
```

**必需列**:
- `timestamps`: 时间戳
- `open`: 开盘价
- `high`: 最高价  
- `low`: 最低价
- `close`: 收盘价
- `volume`: 成交量
- `amount`: 成交额

## 🔄 处理逻辑

### 输入处理流程

```python
# 1. 读取researcher JSON文件（必需）
researcher_data = read_researcher_output("researcher.json")

# 2. 检查CSV数据路径（可选）
if csv_data_path and os.path.exists(csv_data_path):
    # analyst提供了时序数据
    use_provided_csv = True
else:
    # analyst没有提供，查找默认位置
    use_provided_csv = False
    csv_data_path = find_default_csv_data(ticker)

# 3. 智能决策是否使用Kronos
should_use_kronos = evaluate_kronos_need(researcher_data)

# 4. 如果需要且有数据，调用Kronos预测
if should_use_kronos and csv_data_path:
    kronos_result = call_kronos_prediction(ticker, csv_data_path)
else:
    kronos_result = None

# 5. 生成交易决策
decision = generate_decision(researcher_data, kronos_result)
```

### CSV数据处理策略

```python
def handle_csv_data(ticker: str, csv_data_path: str = "") -> str:
    """处理CSV数据路径"""
    
    # 1. 优先使用analyst提供的路径
    if csv_data_path and os.path.exists(csv_data_path):
        return csv_data_path
    
    # 2. 如果没有提供，查找默认位置
    default_paths = [
        f"Kronos/examples/data/US_5min_{ticker}.csv",
        f"Kronos/examples/data/XSHE_5min_{ticker}.csv", 
        f"Kronos/examples/data/XSHG_5min_{ticker}.csv"
    ]
    
    for path in default_paths:
        if os.path.exists(path):
            return path
    
    # 3. 都没有找到，返回None
    return None
```

## 📤 输出规范

### 交易决策卡格式

```json
{
  "ticker": "AAPL",
  "signal": "BUY|SELL|HOLD",
  "size_pct": 0.15,
  "confidence": 0.75,
  "horizon": "5-10 trading days",
  "risk": {
    "stop_loss_pct": 0.08,
    "take_profit_pct": 0.12,
    "max_drawdown_pct": 0.12
  },
  "rationale": [
    "基于研究员分析的关键要点",
    "Kronos AI预测结果（如果使用）"
  ],
  "researcher_summary": {
    "recommendation": "HOLD",
    "confidence": 0.5,
    "net_score": -0.1,
    "uncertainty": 0.3
  },
  "kronos_used": true,
  "csv_data_source": "analyst_provided|default_found|not_available",
  "proposal": "详细的可执行交易提案文本..."
}
```

### 可执行交易提案格式

```
EXECUTABLE TRADING PROPOSAL - BUY AAPL

Position: Open LONG position in AAPL
Size: 15.0% of portfolio
Confidence: 75.0%
Time Horizon: 5-10 trading days

Execution Plan:
1. Market/Limit Order: Buy AAPL shares worth 15.0% of portfolio value
2. Set Stop Loss: 8.0% below entry price
3. Set Take Profit: 12.0% above entry price
4. Review Position: Monitor for 5-10 trading days

Risk Management:
- Maximum loss per trade: 8.0%
- Target profit: 12.0%
- Position size limit: 15.0% of portfolio

Data Sources:
- Researcher Analysis: ✅ 已使用
- Time Series Data: ✅ 来源于analyst
- Kronos AI Prediction: ✅ 已使用

Rationale: 基于研究员深度分析和AI预测的综合判断
```

## 🎯 使用场景

### 场景1: 有完整数据
```python
# analyst提供了CSV时序数据
params = {
    "ticker": "AAPL",
    "researcher_file": "researcher.json",
    "csv_data_path": "analyst_data/AAPL_1min_latest.csv"
}
decision = generate_trading_decision(json.dumps(params))
```

### 场景2: 只有研究报告
```python
# analyst没有提供时序数据
params = {
    "ticker": "AAPL", 
    "researcher_file": "researcher.json"
    # 没有csv_data_path
}
decision = generate_trading_decision(json.dumps(params))
# Trader会查找默认位置或跳过Kronos预测
```

### 场景3: 简化调用
```python
# 使用默认researcher.json
decision = researcher_based_trading_decision("AAPL")
```

## 🤖 Kronos使用逻辑

### 决策因素
1. **研究不确定性** - 如果researcher分析不确定性高
2. **信号中性** - 如果研究结论为中性
3. **数据可用性** - 如果有CSV时序数据可用
4. **时间匹配** - 如果投资时间范围适合AI预测

### 决策矩阵
| 研究信号 | 不确定性 | CSV数据 | 使用Kronos |
|---------|---------|---------|-----------|
| 明确 | 低 | 有/无 | ❌ 不使用 |
| 中性 | 中 | 有 | ✅ 使用 |
| 中性 | 中 | 无 | ⚠️ 查找默认 |
| 中性 | 高 | 有 | ✅ 使用 |
| 中性 | 高 | 无 | ⚠️ Mock预测 |

## 🔧 错误处理

### 输入错误
- **JSON文件缺失**: 返回错误，无法生成决策
- **JSON格式错误**: 尝试解析，使用默认值
- **CSV文件缺失**: 查找默认位置，最后使用Mock预测

### 输出保证
- **始终返回**: 结构化的决策卡
- **始终包含**: 可执行的交易提案
- **错误情况**: 返回HOLD建议和错误说明

## 📋 接口总结

**Trader Agent专注于**:
- ✅ 读取researcher的JSON分析报告
- ✅ 处理analyst的可选CSV时序数据
- ✅ 智能决策是否使用AI预测
- ✅ 生成结构化交易决策
- ✅ 创建可执行交易提案

**Trader Agent不负责**:
- ❌ 股票数据采集
- ❌ 基本面分析
- ❌ 新闻情绪分析
- ❌ 技术指标计算
- ❌ 多维度综合分析

这个设计确保了Trader专注于其核心价值：将研究分析和时序数据转化为可执行的交易决策！
