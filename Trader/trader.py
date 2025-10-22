"""
Trader子Agent - 基于LangChain工具调用的智能交易决策系统
使用大模型作为决策大脑，智能选择和调用交易工具
"""

import os
import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


########################################
#           Trader Tools               #
########################################

def _convert_researcher_to_symbol(ticker, final_decision, analyses):
    """转换单个researcher数据为symbol格式"""
    # 提取current_price
    current_price = 0.0
    market_data = analyses.get("market", {}).get("data", {})
    if isinstance(market_data, dict):
        stock_info = market_data.get("stock_basic_info", {})
        current_price = stock_info.get("current_price", 0.0)
    
    # 从scorecard提取不确定性级别
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
    """加载和解析研究团队的分析结论，支持单股票和多股票"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 情况1: 单个researcher输出
        if "final_decision" in data and "ticker" in data:
            symbol = _convert_researcher_to_symbol(
                data.get("ticker", "UNKNOWN"),
                data.get("final_decision", {}),
                data.get("analyses", {})
            )
            # 添加CSV路径（如果存在）
            csv_path = data.get("csv_path")
            if csv_path:
                symbol["csv_path"] = csv_path
                print(f"📊 找到CSV文件: {csv_path}")
            converted_data = {"symbols": [symbol]}
            print(f"✅ 成功加载研究数据: 1个股票 (Researcher格式)")
            return json.dumps(converted_data, ensure_ascii=False)
        
        # 情况2: 多个researcher输出列表
        elif isinstance(data, list):
            symbols = []
            for item in data:
                if "final_decision" in item and "ticker" in item:
                    symbol = _convert_researcher_to_symbol(
                        item.get("ticker", "UNKNOWN"),
                        item.get("final_decision", {}),
                        item.get("analyses", {})
                    )
                    # 添加CSV路径（如果存在）
                    csv_path = item.get("csv_path")
                    if csv_path:
                        symbol["csv_path"] = csv_path
                    symbols.append(symbol)
            converted_data = {"symbols": symbols}
            print(f"✅ 成功加载研究数据: {len(symbols)}个股票 (Researcher列表格式)")
            return json.dumps(converted_data, ensure_ascii=False)
        
        # 情况3: 原始symbols格式
        else:
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
        from model import Kronos, KronosTokenizer, KronosPredictor
        
        # 加载数据
        df = pd.read_csv(csv_file_path)
        
        # 列名映射（中文→英文）
        column_mapping = {
            '日期': 'timestamp',
            '开盘价': 'open',
            '最高价': 'high',
            '最低价': 'low',
            '收盘价': 'close',
            '成交量': 'volume'
        }
        df.rename(columns=column_mapping, inplace=True)
        
        # 计算amount字段（如果不存在）
        if 'amount' not in df.columns and 'close' in df.columns and 'volume' in df.columns:
            df['amount'] = df['close'] * df['volume']
        
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
        
        # 执行预测
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
        
        # 创建输出目录
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = os.path.join("database", today, symbol, "Kronos_output")
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 1. 保存预测CSV（添加时间戳列）
        pred_df_with_time = pred_df.copy()
        pred_df_with_time.insert(0, 'timestamp', y_timestamp)
        csv_path = os.path.join(output_dir, f"{symbol}_prediction_{timestamp_str}.csv")
        pred_df_with_time.to_csv(csv_path, index=False)
        
        # 2. 保存专业金融预测图像
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.patches import Rectangle
        
        # 设置专业金融图表样式
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # 设置英文字体
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        
        fig, ax = plt.subplots(figsize=(14, 8), facecolor='white')
        
        # 准备时间轴数据
        hist_length = min(60, len(df))  # 显示最近60天历史数据
        hist_close = df['close'].tail(hist_length)
        hist_timestamps = df[timestamp_col].tail(hist_length)
        pred_close = pred_df['close']
        
        # 转换时间戳
        hist_dates = pd.to_datetime(hist_timestamps)
        pred_dates = pd.to_datetime(y_timestamp)
        
        # 绘制历史价格（深蓝色实线）
        ax.plot(hist_dates, hist_close, 
                color='#1f77b4', linewidth=2.5, 
                label=f'Historical Price ({hist_length} days)', alpha=0.9)
        
        # 绘制预测价格（红色虚线）
        ax.plot(pred_dates, pred_close, 
                color='#d62728', linewidth=2.5, linestyle='--', 
                label=f'Kronos Prediction ({len(pred_close)} days)', alpha=0.9)
        
        # 添加预测区间阴影
        pred_min = pred_close.min()
        pred_max = pred_close.max()
        ax.fill_between(pred_dates, pred_min, pred_max, 
                       color='#d62728', alpha=0.1, 
                       label=f'Prediction Range (${pred_min:.2f} - ${pred_max:.2f})')
        
        # 在历史和预测之间添加分割线
        transition_date = hist_dates.iloc[-1]
        ax.axvline(x=transition_date, color='gray', linestyle=':', alpha=0.7, linewidth=1.5)
        ax.text(transition_date, ax.get_ylim()[1]*0.95, 'Prediction Start', 
                rotation=90, ha='right', va='top', fontsize=10, color='gray')
        
        # 设置专业的标题和标签
        current_price = hist_close.iloc[-1]
        pred_mean = pred_close.mean()
        change_pct = ((pred_mean - current_price) / current_price) * 100
        
        ax.set_title(f'{symbol} Stock Price Prediction Analysis | Kronos AI Model\n'
                    f'Current Price: ${current_price:.2f} → Predicted Avg: ${pred_mean:.2f} '
                    f'({change_pct:+.1f}%)', 
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_ylabel('Stock Price (USD)', fontsize=12, fontweight='bold')
        ax.set_xlabel('Time', fontsize=12, fontweight='bold')
        
        # 设置时间轴格式
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 设置网格
        ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
        ax.set_facecolor('#fafafa')
        
        # 设置图例
        legend = ax.legend(loc='upper left', frameon=True, fancybox=True, shadow=True)
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_alpha(0.9)
        
        # 添加价格统计信息
        stats_text = f'''Prediction Statistics:
Min Price: ${pred_close.min():.2f}
Max Price: ${pred_close.max():.2f}
Avg Price: ${pred_close.mean():.2f}
Std Dev: ${pred_close.std():.2f}
Forecast Days: {len(pred_close)}'''
        
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
                verticalalignment='top', bbox=dict(boxstyle='round', 
                facecolor='white', alpha=0.8), fontsize=10)
        
        # 设置Y轴格式（显示美元符号）
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:.0f}'))
        
        # 调整布局
        plt.tight_layout()
        
        # 保存高质量图片
        plot_path = os.path.join(output_dir, f"{symbol}_prediction_{timestamp_str}.png")
        plt.savefig(plot_path, dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        plt.close()
        
        # 3. 保存元数据
        metadata = {
            "symbol": symbol,
            "prediction_time": datetime.now().isoformat(),
            "input_csv": csv_file_path,
            "prediction_length": prediction_length,
            "lookback_length": lookback,
            "prediction_summary": {
                "min_price": float(pred_df['close'].min()),
                "max_price": float(pred_df['close'].max()),
                "mean_price": float(pred_df['close'].mean()),
                "std_price": float(pred_df['close'].std())
            },
            "output_files": {
                "csv": csv_path,
                "plot": plot_path
            }
        }
        
        metadata_path = os.path.join(output_dir, f"{symbol}_metadata_{timestamp_str}.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # 返回结果
        result = {
            "symbol": symbol,
            "output_dir": output_dir,
            "csv_path": csv_path,
            "plot_path": plot_path,
            "metadata_path": metadata_path,
            "prediction_summary": metadata["prediction_summary"]
        }
        
        print(f"✅ Kronos预测完成: {symbol}")
        print(f"   📁 输出目录: {output_dir}")
        print(f"   📊 CSV文件: {os.path.basename(csv_path)}")
        print(f"   📈 图表文件: {os.path.basename(plot_path)}")
        print(f"   📝 元数据文件: {os.path.basename(metadata_path)}")
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        print(f"❌ Kronos预测失败: {e}")
        return json.dumps({"error": str(e), "symbol": symbol}, ensure_ascii=False)


@tool
def generate_decision_card(symbol: str, current_price: float, recommendation: str, 
                          confidence: float, reasoning: str, prediction_data: Optional[str] = None) -> str:
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
        # 设置模型所需的 OpenAI API 密钥
        if not openai_api_key:
            openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 未配置，Trader Agent 无法调用 OpenAI 接口。")
        os.environ["OPENAI_API_KEY"] = openai_api_key
        
        self.agent_executor = self._build_agent()
        print("✅ Trader Agent初始化成功")
    
    def _build_agent(self) -> AgentExecutor:
        """构建Trader Agent"""
        tools = [load_research_data, run_kronos_prediction, generate_decision_card]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "你是一个专业的量化交易Agent，负责分析研究团队的结论并生成交易决策。\n"
             "工作流程：\n"
             "1. load_research_data加载研究数据（自动包含csv_path字段）\n"
             "2. 分析用户请求，判断是否需要Kronos预测\n"
             "3. 如需Kronos预测：run_kronos_prediction(csv_file_path=symbol['csv_path'], symbol=symbol['symbol'])\n"
             "4. generate_decision_card生成决策卡（可选传入prediction_data）\n"
             "Kronos调用决策：\n"
             "- 用户明确要求预测/价格预测/未来走势/Kronos时，必须调用Kronos\n"
             "- 用户要求完整分析/全面分析时，建议调用Kronos\n"
             "- uncertainty_level为high/very_high时，建议调用Kronos\n"
             "- 只要csv_path存在且用户有预测需求，就应该调用Kronos\n"
             "- 综合研究结论和预测结果做出最终决策\n"
             "请按照工作流程完成任务。"),
            MessagesPlaceholder("chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        
        llm = ChatOpenAI(
                model="qwen/qwen3-235b-a22b",
                temperature=0.1,
                base_url="https://zehenglmstudio.cpolar.top/v1"
            )
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
