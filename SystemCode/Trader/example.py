"""
Trader agent tool invocation example.
Demonstrates the tool-driven smart trading decision workflow.
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from trader import Trader


def create_research_conclusion() -> str:
    """Create a sample research-team conclusion."""
    research_data = {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "analyst_team": "MarketLens Research Team",
        "market_outlook": "BULLISH",
        "uncertainty_level": "high",
        "use_kronos_prediction": True,
        "key_themes": ["Tech rebound", "AI momentum", "Earnings growth outlook"],
        "symbols": [
            {
                "symbol": "AAPL",
                "current_price": 175.50,
                "recommendation": "BUY",
                "confidence": 0.75,
                "reasoning": "iPhone 15 sales exceeded expectations; services revenue accelerating",
                "risk_level": "MEDIUM",
                "time_horizon": "3-6 months"
            },
            {
                "symbol": "TSLA", 
                "current_price": 245.80,
                "recommendation": "HOLD",
                "confidence": 0.60,
                "reasoning": "Deliveries are growing but competition is intensifying; wait for catalysts",
                "risk_level": "HIGH",
                "time_horizon": "1-3 months"
            }
        ]
    }
    
    filename = "research_conclusion.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(research_data, f, indent=2, ensure_ascii=False)
    print(f"Created research conclusion file: {filename}")
    return filename

def create_sample_data(symbol: str, days: int = 30) -> str:
    """Create a sample CSV time-series file."""
    # Generate timestamps
    timestamps = pd.date_range(start=datetime.now() - timedelta(days=days), 
                              end=datetime.now(), freq='1H')
    
    # Generate random-walk price data
    np.random.seed(42)
    price = 100.0
    data = []
    
    for ts in timestamps:
        change = np.random.normal(0, 0.02)  # Approx. 2% volatility
        price *= (1 + change)
        
        # Build OHLCV snapshot
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
            'amount': close * volume  # Include traded notional
        })
        price = close
    
    # Persist CSV to disk
    df = pd.DataFrame(data)
    filename = f"{symbol}_data.csv"
    df.to_csv(filename, index=False)
    
    # Sanity-check generated data
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount']
    actual_cols = df.columns.tolist()
    print(f"Created sample data: {filename} ({len(df)} rows)")
    print(f"  Columns: {actual_cols}")
    print(f"  Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return filename


def main():
    """Entry point."""
    print("=== Trader agent tool invocation demo ===\n")
    
    # 1. Create research conclusion artifact
    research_file = create_research_conclusion()
    
    # 2. Produce sample CSVs for Kronos predictions
    csv_files = []
    for symbol in ['AAPL', 'TSLA']:
        csv_file = create_sample_data(symbol, days=50)
        csv_files.append(csv_file)
    
    # 3. Initialize trader agent
    print("\nInitializing Trader agent...")
    trader = Trader()
    
    # Display available tools
    print(f"Available tools: {trader.get_available_tools()}")
    
    # 4. Invoke via the primary agent interface
    print("\nMode 1: direct agent call")
    result1 = trader.analyze_and_decide(research_file, csv_files)
    print("Result 1:", result1[:200] + "..." if len(result1) > 200 else result1)
    
    # 5. Invoke via natural-language request
    print("\nMode 2: natural language request (explicitly skip Kronos)")
    result2 = trader.process_request(
        "Review the research team conclusions, skip Kronos forecasting, and produce the trading decision card directly.",
        research_file,
        csv_files
    )
    
    # 6. Display agent output
    print(f"\n=== Agent output ===")
    print("Result 2:", result2[:500] + "..." if len(result2) > 500 else result2)
    
    # 7. Clean up artifacts
    import os
    for file in csv_files + [research_file]:
        if os.path.exists(file):
            os.remove(file)
    
    # Remove generated prediction images
    import glob
    prediction_images = glob.glob("prediction_*.png")
    for img in prediction_images:
        if os.path.exists(img):
            os.remove(img)
            print(f"Removed prediction image: {img}")
    
    print(f"\n✅ Temporary files cleaned up")


if __name__ == "__main__":
    main()
