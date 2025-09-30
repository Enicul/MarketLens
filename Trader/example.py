"""
Trader Agent工具调用示例
演示基于工具调用的智能交易决策系统
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from trader import Trader


def create_research_conclusion() -> str:
    """创建研究团队结论示例"""
    research_data = {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "analyst_team": "MarketLens研究团队",
        "market_outlook": "BULLISH",
        "uncertainty_level": "high",
        "use_kronos_prediction": True,
        "key_themes": ["科技股反弹", "AI概念热潮", "业绩增长预期"],
        "symbols": [
            {
                "symbol": "AAPL",
                "current_price": 175.50,
                "recommendation": "BUY",
                "confidence": 0.75,
                "reasoning": "iPhone 15销售超预期，服务业务增长强劲",
                "risk_level": "MEDIUM",
                "time_horizon": "3-6个月"
            },
            {
                "symbol": "TSLA", 
                "current_price": 245.80,
                "recommendation": "HOLD",
                "confidence": 0.60,
                "reasoning": "交付量增长但竞争加剧，等待更多催化剂",
                "risk_level": "HIGH",
                "time_horizon": "1-3个月"
            }
        ]
    }
    
    filename = "research_conclusion.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(research_data, f, indent=2, ensure_ascii=False)
    print(f"创建研究结论文件: {filename}")
    return filename

def create_sample_data(symbol: str, days: int = 30) -> str:
    """创建示例CSV数据文件"""
    # 生成时间序列
    timestamps = pd.date_range(start=datetime.now() - timedelta(days=days), 
                              end=datetime.now(), freq='1H')
    
    # 生成价格数据（随机游走）
    np.random.seed(42)
    price = 100.0
    data = []
    
    for ts in timestamps:
        change = np.random.normal(0, 0.02)  # 2%波动
        price *= (1 + change)
        
        # 生成OHLC
        open_price = price
        high = price * np.random.uniform(1.0, 1.03)
        low = price * np.random.uniform(0.97, 1.0)
        close = price * np.random.uniform(0.99, 1.01)
        volume = np.random.randint(1000, 10000)
        
        data.append({
            'timestamp': ts,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'amount': close * volume  # 添加amount列
        })
        price = close
    
    # 保存CSV文件
    df = pd.DataFrame(data)
    filename = f"{symbol}_data.csv"
    df.to_csv(filename, index=False)
    
    # 验证生成的数据
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']
    actual_cols = df.columns.tolist()
    print(f"创建示例数据: {filename} ({len(df)}条记录)")
    print(f"  包含列: {actual_cols}")
    print(f"  时间范围: {df['timestamp'].min()} 到 {df['timestamp'].max()}")
    
    return filename


def main():
    """主函数"""
    print("=== Trader Agent工具调用示例 ===\n")
    
    # 1. 创建研究团队结论
    research_file = create_research_conclusion()
    
    # 2. 创建示例数据（用于Kronos预测）
    csv_files = []
    for symbol in ['AAPL', 'TSLA']:
        csv_file = create_sample_data(symbol, days=50)
        csv_files.append(csv_file)
    
    # 3. 初始化Trader Agent
    print("\n初始化Trader Agent...")
    trader = Trader()
    
    # 显示可用工具
    print(f"可用工具: {trader.get_available_tools()}")
    
    # 4. 通过主Agent接口调用
    print("\n方式1: 主Agent调用接口")
    result1 = trader.analyze_and_decide(research_file, csv_files)
    print("结果1:", result1[:200] + "..." if len(result1) > 200 else result1)
    
    # 5. 通过自然语言请求调用
    print("\n方式2: 自然语言请求（明确拒绝Kronos）")
    result2 = trader.process_request(
        "请分析研究团队的结论，不要使用Kronos预测，直接生成交易决策卡",
        research_file,
        csv_files
    )
    
    # 6. 显示Agent结果
    print(f"\n=== Agent执行结果 ===")
    print("结果2:", result2[:500] + "..." if len(result2) > 500 else result2)
    
    # 7. 清理文件
    import os
    for file in csv_files + [research_file]:
        if os.path.exists(file):
            os.remove(file)
    
    # 清理生成的预测图
    import glob
    prediction_images = glob.glob("prediction_*.png")
    for img in prediction_images:
        if os.path.exists(img):
            os.remove(img)
            print(f"清理预测图: {img}")
    
    print(f"\n✅ 清理临时文件完成")


if __name__ == "__main__":
    main()
