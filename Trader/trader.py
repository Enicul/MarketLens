"""
Trader子Agent - 基于LangChain工具调用的智能交易决策系统
使用大模型作为决策大脑，智能选择和调用交易工具
"""

import os
import json
import pandas as pd
from typing import Dict, List
from datetime import datetime

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


########################################
#           Trader Tools               #
########################################

@tool
def load_research_data(json_file_path: str) -> str:
    """加载和解析研究团队的分析结论"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ 成功加载研究数据: {len(data.get('symbols', []))}个股票")
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"加载研究数据失败: {e}"}, ensure_ascii=False)


@tool
def run_kronos_prediction(csv_file_path: str, symbol: str, prediction_length: int = 120) -> str:
    """使用Kronos模型进行股价预测。仅在用户明确要求或研究结论建议使用预测时调用。"""
    try:
        import sys
        sys.path.append(os.path.join(os.path.dirname(__file__), 'Kronos'))
        from Kronos.model import Kronos, KronosTokenizer, KronosPredictor
        
        # 加载数据（使用CSV文件中的所有参数）
        df = pd.read_csv(csv_file_path)
        
        # 验证必需列
        required_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"CSV文件缺少列: {missing_cols}")
        
        # 找到时间戳列
        timestamp_col = next((col for col in ['timestamp', 'timestamps', 'datetime'] if col in df.columns), None)
        if not timestamp_col:
            raise ValueError("CSV文件缺少时间戳列")
        
        df[timestamp_col] = pd.to_datetime(df[timestamp_col])
        
        # 初始化Kronos模型
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
        predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)
        
        # 准备预测数据（使用CSV文件中的完整参数）
        lookback = min(400, len(df))
        x_df = df.tail(lookback)[required_cols].reset_index(drop=True)
        x_timestamp = df.tail(lookback)[timestamp_col].reset_index(drop=True)
        
        # 生成未来时间戳（基于CSV文件的时间间隔）
        if len(x_timestamp) > 1:
            time_delta = x_timestamp.iloc[-1] - x_timestamp.iloc[-2]
            y_timestamp = pd.date_range(start=x_timestamp.iloc[-1], periods=prediction_length+1, freq=time_delta)[1:]
        else:
            y_timestamp = pd.date_range(start=x_timestamp.iloc[-1], periods=prediction_length+1, freq='5min')[1:]
        
        # 执行预测（确保时间戳格式正确）
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
        
        # 生成简洁的预测图
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(10, 6))
        
        # 绘制历史和预测价格
        hist_close = df['close'].tail(100)
        pred_close = pred_df['close']
        
        hist_x = range(len(hist_close))
        pred_x = range(len(hist_close), len(hist_close) + len(pred_close))
        
        plt.plot(hist_x, hist_close, label='Historical', color='blue', linewidth=2)
        plt.plot(pred_x, pred_close, label='Predicted', color='red', linewidth=2, linestyle='--')
        plt.title(f'{symbol} Price Prediction')
        plt.ylabel('Price')
        plt.xlabel('Time Points')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # 保存图片
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plot_path = f"prediction_{symbol}_{timestamp}.png"
        plt.savefig(plot_path, dpi=100, bbox_inches='tight')
        plt.close()
        
        # 预测结果
        result = {
            "symbol": symbol,
            "plot_path": plot_path,
            "prediction_summary": {
                "min_price": float(pred_df['close'].min()),
                "max_price": float(pred_df['close'].max()),
                "mean_price": float(pred_df['close'].mean()),
                "prediction_length": len(pred_df)
            }
        }
        
        print(f"✅ Kronos预测完成: {symbol}")
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        print(f"❌ Kronos预测失败: {e}")
        return json.dumps({"error": str(e), "symbol": symbol}, ensure_ascii=False)


@tool
def generate_decision_card(symbol: str, current_price: float, recommendation: str, 
                          confidence: float, reasoning: str, prediction_data: str = None) -> str:
    """生成标准化交易决策卡"""
    try:
        # 解析预测数据
        pred_data = None
        if prediction_data:
            try:
                pred_data = json.loads(prediction_data)
            except:
                pass
        
        # 基础决策卡
        card = {
            "symbol": symbol,
            "decision": recommendation.upper(),
            "confidence_score": round(confidence, 3),
            "current_price": current_price,
            "reasoning": reasoning,
            "has_prediction": bool(pred_data),
            "timestamp": datetime.now().isoformat()
        }
        
        # 如果有预测数据，调整决策
        if pred_data and "prediction_summary" in pred_data:
            pred_summary = pred_data["prediction_summary"]
            pred_mean = pred_summary["mean_price"]
            price_change = (pred_mean - current_price) / current_price
            
            # 基于预测调整置信度
            if abs(price_change) > 0.05:  # 预测变化超过5%
                if (price_change > 0 and recommendation.upper() == "BUY") or (price_change < 0 and recommendation.upper() == "SELL"):
                    confidence = min(0.9, confidence + 0.1)  # 提高置信度
                else:
                    confidence = max(0.3, confidence - 0.1)  # 降低置信度
            
            card["confidence_score"] = round(confidence, 3)
            card["prediction_insight"] = f"预测价格变化: {price_change:.2%}"
        
        # 计算风险参数
        risk_metrics = _calculate_risk_metrics(current_price, recommendation.upper(), confidence)
        card.update(risk_metrics)
        
        print(f"✅ 生成决策卡: {symbol} - {recommendation}")
        return json.dumps(card, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({"error": f"生成决策卡失败: {e}", "symbol": symbol}, ensure_ascii=False)


def _calculate_risk_metrics(current_price: float, signal: str, confidence: float) -> Dict:
    """计算风险指标"""
    # 仓位计算
    base_position = 0.1 if signal in ['BUY', 'SELL'] else 0
    position_size = base_position * confidence
    position_size = min(position_size, 0.2)  # 最大20%
    
    # 止损止盈
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
            "description": f"建议仓位{position_size*100:.1f}%"
        },
        "execution_range": {
            "min_price": round(current_price * 0.98, 4),
            "max_price": round(current_price * 1.02, 4),
            "description": "在当前价格±2%区间内执行"
        },
        "stop_loss": {
            "price": stop_loss,
            "description": f"止损价格{stop_loss}" if stop_loss else "无止损设置"
        },
        "take_profit": {
            "price": take_profit,
            "description": f"止盈价格{take_profit}" if take_profit else "无止盈设置"
        }
    }


########################################
#        Trader Agent                  #
########################################

class Trader:
    """
    智能交易Agent - 基于LangChain工具调用的决策系统
    """
    
    def __init__(self, openai_api_key: str = None):
        """初始化Trader Agent"""
        # 设置OpenAI API密钥
        if openai_api_key:
            os.environ['OPENAI_API_KEY'] = openai_api_key
        elif not os.environ.get('OPENAI_API_KEY'):
            os.environ['OPENAI_API_KEY'] = "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"
        
        self.agent_executor = self._build_agent()
        print("✅ Trader Agent初始化成功")
    
    def _build_agent(self) -> AgentExecutor:
        """构建Trader Agent"""
        tools = [load_research_data, run_kronos_prediction, generate_decision_card]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "你是一个专业的量化交易Agent，负责分析研究团队的结论并生成交易决策。\n"
             "工作流程：\n"
             "1. 使用load_research_data工具加载研究团队的分析结论\n"
             "2. 根据研究结论的不确定性和建议，决定是否使用run_kronos_prediction工具进行价格预测\n"
             "3. 使用generate_decision_card工具为每个股票生成标准化决策卡\n"
             "决策原则：\n"
             "- 当uncertainty_level为high或very_high时，建议使用Kronos预测\n"
             "- 当研究结论中use_kronos_prediction为true时，必须使用预测\n"
             "- 综合研究结论和预测结果做出最终决策\n"
             "- 严格控制风险，合理设置仓位和止损止盈\n"
             "请按照工作流程，智能选择和调用工具完成任务。"),
            MessagesPlaceholder("chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
        agent = create_tool_calling_agent(llm, tools, prompt)
        
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
        )
    
    def analyze_and_decide(self, research_json: str, csv_files: List[str] = None, use_kronos: bool = None) -> str:
        """主Agent调用接口 - 分析并生成交易决策"""
        if use_kronos is False:
            request = f"请基于研究结论生成交易决策卡，不要使用Kronos预测。研究文件: {research_json}"
        elif use_kronos is True:
            csv_info = f"，CSV文件: {', '.join(csv_files)}" if csv_files else ""
            request = f"请基于研究结论生成交易决策卡，必须使用Kronos预测。研究文件: {research_json}{csv_info}"
        else:
            csv_info = f"，CSV文件: {', '.join(csv_files)}" if csv_files else ""
            request = f"请基于研究结论生成交易决策卡，根据研究建议决定是否使用Kronos预测。研究文件: {research_json}{csv_info}"
        
        try:
            result = self.agent_executor.invoke({"input": request, "chat_history": []})
            return result["output"]
        except Exception as e:
            return f"❌ 分析失败: {str(e)}"
    
    def process_request(self, user_request: str, research_json: str = None, csv_files: List[str] = None) -> str:
        """处理自然语言请求"""
        context = ""
        if research_json:
            context += f"研究结论文件: {research_json}。"
        if csv_files:
            context += f"可用数据文件: {', '.join(csv_files)}。"
        
        full_request = f"{user_request}。{context}"
        
        try:
            result = self.agent_executor.invoke({"input": full_request, "chat_history": []})
            return result["output"]
        except Exception as e:
            return f"❌ 处理失败: {str(e)}"
    
    def get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        return [tool.name for tool in self.agent_executor.tools]