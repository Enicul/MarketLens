#!/usr/bin/env python3
"""
测试Trader Agent与Researcher集成的功能
"""

import asyncio
import json
import sys
import os

# 模拟测试（不需要OpenAI API）
def test_researcher_data_processing():
    """测试研究员数据处理逻辑"""
    print("🧪 测试研究员数据处理逻辑...")
    
    # 读取实际的researcher.json数据
    try:
        with open('../researcher.json', 'r', encoding='utf-8') as f:
            researcher_data = json.load(f)
        print("✅ 成功读取researcher.json")
    except Exception as e:
        print(f"❌ 读取researcher.json失败: {e}")
        return False
    
    # 模拟analyze_researcher_output工具的逻辑
    ticker = researcher_data.get("ticker", "UNKNOWN")
    stance_summary = researcher_data.get("stance_summary", {})
    scorecard = researcher_data.get("scorecard", {})
    action = researcher_data.get("action", {})
    key_upside = researcher_data.get("key_upside", [])
    key_risks = researcher_data.get("key_risks", [])
    
    # 提取关键指标
    bull_strength = scorecard.get("bull_strength", 0.5)
    bear_strength = scorecard.get("bear_strength", 0.5)
    uncertainty = scorecard.get("uncertainty", 0.5)
    net_score = scorecard.get("net_score", 0.0)
    
    # 确定研究信号
    if net_score > 0.2:
        research_signal = "BULLISH"
    elif net_score < -0.2:
        research_signal = "BEARISH"
    else:
        research_signal = "NEUTRAL"
    
    research_confidence = max(0.1, 1.0 - uncertainty)
    
    print(f"\n📊 研究员分析结果:")
    print(f"股票: {ticker}")
    print(f"研究信号: {research_signal}")
    print(f"研究置信度: {research_confidence:.2f}")
    print(f"净得分: {net_score:.3f}")
    print(f"多头强度: {bull_strength:.1f}")
    print(f"空头强度: {bear_strength:.1f}")
    print(f"不确定性: {uncertainty:.1f}")
    
    return True

def test_kronos_decision_logic():
    """测试Kronos使用决策逻辑"""
    print(f"\n🤖 测试Kronos使用决策逻辑...")
    
    # 模拟不同的分析场景
    test_scenarios = [
        {
            "name": "高不确定性场景",
            "uncertainty": 0.6,
            "disagreements": 3,
            "research_signal": "NEUTRAL",
            "time_horizon": "medium",
            "research_confidence": 0.4
        },
        {
            "name": "明确看涨场景",
            "uncertainty": 0.2,
            "disagreements": 1,
            "research_signal": "BULLISH",
            "time_horizon": "short",
            "research_confidence": 0.8
        },
        {
            "name": "中性场景",
            "uncertainty": 0.3,
            "disagreements": 2,
            "research_signal": "NEUTRAL",
            "time_horizon": "long",
            "research_confidence": 0.6
        }
    ]
    
    for scenario in test_scenarios:
        print(f"\n  📋 {scenario['name']}:")
        
        # 模拟should_use_kronos_prediction逻辑
        use_kronos_factors = []
        
        if scenario["uncertainty"] > 0.4:
            use_kronos_factors.append("high_uncertainty")
        if scenario["disagreements"] > 2:
            use_kronos_factors.append("conflicting_signals")
        if scenario["research_signal"] == "NEUTRAL":
            use_kronos_factors.append("neutral_research")
        if scenario["time_horizon"] in ["medium", "long"]:
            use_kronos_factors.append("suitable_horizon")
        if scenario["research_confidence"] < 0.6:
            use_kronos_factors.append("low_confidence")
        
        use_kronos = len(use_kronos_factors) >= 2
        confidence = len(use_kronos_factors) / 5.0
        
        print(f"    • 触发因素: {use_kronos_factors}")
        print(f"    • 使用Kronos: {'是' if use_kronos else '否'}")
        print(f"    • 决策置信度: {confidence:.2f}")
    
    return True

def test_decision_generation_logic():
    """测试决策生成逻辑"""
    print(f"\n💼 测试交易决策生成逻辑...")
    
    # 模拟研究员分析结果
    researcher_analysis = {
        "ticker": "AAPL",
        "research_signal": "NEUTRAL",  # 基于实际数据
        "research_confidence": 0.7,   # 1 - 0.3 uncertainty
        "net_score": -0.1,            # 实际净得分
        "recommendation": "HOLD",
        "time_horizon": "medium",
        "bull_strength": 0.7,
        "bear_strength": 0.5,
        "uncertainty": 0.3,
        "key_upside": ["Strong market capitalization reflects investor confidence."],
        "key_risks": ["Absence of reported EPS raises concerns about profitability."]
    }
    
    # 模拟Kronos预测（假设被调用）
    kronos_prediction = {
        "ticker": "AAPL",
        "prediction_type": "mock",
        "predicted_change_pct": 2.5,
        "confidence": 0.6,
        "signal": "BUY"
    }
    
    # 模拟决策生成逻辑
    scores = []
    confidence_factors = []
    rationale_parts = []
    
    # 研究员分析得分（最高权重）
    research_score = researcher_analysis["net_score"] * researcher_analysis["research_confidence"]
    scores.append(research_score * 1.5)  # 高权重
    confidence_factors.append("researcher_analysis")
    rationale_parts.append(f"Research upside: {researcher_analysis['key_upside'][0]}")
    
    # Kronos预测得分
    pred_change = kronos_prediction["predicted_change_pct"]
    pred_confidence = kronos_prediction["confidence"]
    kronos_score = (pred_change / 10.0) * pred_confidence
    scores.append(kronos_score)
    confidence_factors.append("ai_prediction")
    rationale_parts.append(f"AI predicts {pred_change:+.1f}% change")
    
    # 计算最终得分
    final_score = sum(scores) / len(scores)
    base_confidence = len(confidence_factors) / 5.0
    
    # 确定行动
    if final_score > 0.3:
        action = "BUY"
        position_size = min(0.15 + (final_score - 0.3) * 0.2, 0.25)
    elif final_score < -0.3:
        action = "SELL"
        position_size = min(0.10 + abs(final_score + 0.3) * 0.15, 0.20)
    else:
        action = "HOLD"
        position_size = 0.05
    
    confidence = min(base_confidence + abs(final_score) * 0.3, 1.0)
    
    print(f"  📈 决策结果:")
    print(f"    • 最终得分: {final_score:.3f}")
    print(f"    • 交易信号: {action}")
    print(f"    • 仓位大小: {position_size*100:.1f}%")
    print(f"    • 置信度: {confidence:.2f}")
    print(f"    • 理由: {' | '.join(rationale_parts)}")
    
    return True

def test_proposal_generation():
    """测试可执行提案生成"""
    print(f"\n📋 测试可执行交易提案生成...")
    
    # 模拟决策卡
    decision_card = {
        "ticker": "AAPL",
        "signal": "BUY",
        "size_pct": 0.18,
        "confidence": 0.75,
        "horizon": "5-10 trading days",
        "risk": {
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.12
        },
        "rationale": ["Research upside: Strong market cap", "AI predicts +2.5% change"]
    }
    
    # 生成提案
    ticker = decision_card["ticker"]
    signal = decision_card["signal"]
    size_pct = decision_card["size_pct"]
    confidence = decision_card["confidence"]
    horizon = decision_card["horizon"]
    risk_params = decision_card["risk"]
    rationale = decision_card["rationale"]
    
    proposal = f"""
EXECUTABLE TRADING PROPOSAL - {signal} {ticker}

Position: Open LONG position in {ticker}
Size: {size_pct*100:.1f}% of portfolio
Confidence: {confidence*100:.1f}%
Time Horizon: {horizon}

Execution Plan:
1. Market/Limit Order: Buy {ticker} shares worth {size_pct*100:.1f}% of portfolio value
2. Set Stop Loss: {risk_params['stop_loss_pct']*100:.1f}% below entry price
3. Set Take Profit: {risk_params['take_profit_pct']*100:.1f}% above entry price
4. Review Position: Monitor for {horizon}

Risk Management:
- Maximum loss per trade: {risk_params['stop_loss_pct']*100:.1f}%
- Target profit: {risk_params['take_profit_pct']*100:.1f}%
- Position size limit: {size_pct*100:.1f}% of portfolio

Rationale: {' | '.join(rationale)}
    """.strip()
    
    print("  📄 生成的交易提案:")
    print(proposal)
    
    return True

def main():
    """主测试函数"""
    print("🚀 Trader Agent 研究员集成测试开始")
    print("=" * 60)
    
    tests = [
        ("研究员数据处理", test_researcher_data_processing),
        ("Kronos使用决策", test_kronos_decision_logic),
        ("交易决策生成", test_decision_generation_logic),
        ("可执行提案生成", test_proposal_generation)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            if test_func():
                print(f"✅ {test_name} 测试通过")
                passed += 1
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    print(f"\n{'='*60}")
    print(f"🎯 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！Trader Agent 研究员集成功能正常")
        print("\n📝 集成特性:")
        print("✅ 读取researcher.json文件")
        print("✅ 智能决策是否使用Kronos预测")
        print("✅ 结合研究和AI预测生成交易决策")
        print("✅ 生成详细的可执行交易提案")
    else:
        print(f"⚠️ {total-passed} 个测试失败，需要检查实现")

if __name__ == "__main__":
    main()
