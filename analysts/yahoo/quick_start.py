"""
Yahoo Finance 工具快速开始脚本
python quick_start.py
一键安装依赖并运行示例
"""

import subprocess
import sys
import os

def install_dependencies():
    """安装依赖包"""
    print("正在安装依赖包...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✓ 依赖包安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 依赖包安装失败: {e}")
        return False

def run_example():
    """运行示例"""
    print("\n运行 Yahoo Finance 工具示例...")
    try:
        from yahoo import YahooFinanceTool
        
        # 创建工具
        tool = YahooFinanceTool()
        
        # 示例1: 获取股票信息
        print("\n=== 示例1: 获取苹果股票信息 ===")
        try:
            stock_info = tool.get_stock_info("AAPL")
            print(f"股票代码: {stock_info.ticker}")
            print(f"当前价格: ${stock_info.current_price}")
            print(f"涨跌幅: {stock_info.change_percent:+.2f}%")
            print(f"成交量: {stock_info.volume:,}")
            if stock_info.market_cap:
                print(f"市值: ${stock_info.market_cap:,}")
        except Exception as e:
            print(f"获取股票信息失败: {e}")
        
        # 示例2: 获取历史数据
        print("\n=== 示例2: 获取历史数据 ===")
        try:
            hist_data = tool.get_historical_data("AAPL", period="5d")
            print(f"数据点数: {hist_data.data_points}")
            print(f"时间范围: {hist_data.start_date} 到 {hist_data.end_date}")
            if not hist_data.data.empty:
                latest_price = hist_data.data['Close'].iloc[-1]
                print(f"最新收盘价: ${latest_price:.2f}")
        except Exception as e:
            print(f"获取历史数据失败: {e}")
        
        # 示例3: 搜索股票
        print("\n=== 示例3: 搜索股票 ===")
        try:
            search_results = tool.search_stocks("Apple", max_results=3)
            print(f"搜索到 {len(search_results)} 个结果:")
            for result in search_results:
                print(f"  {result['symbol']}: {result['name']}")
        except Exception as e:
            print(f"搜索股票失败: {e}")
        
        # 示例4: 获取市场概况
        print("\n=== 示例4: 获取市场概况 ===")
        try:
            market_summary = tool.get_market_summary()
            print("主要指数:")
            for index, data in market_summary.items():
                print(f"  {index}: {data['price']} ({data['change_percent']:+.2f}%)")
        except Exception as e:
            print(f"获取市场概况失败: {e}")
        
        print("\n✓ 示例运行完成")
        return True
        
    except ImportError as e:
        print(f"✗ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"✗ 运行示例失败: {e}")
        return False

def run_test():
    """运行测试"""
    print("\n运行测试...")
    try:
        import test_yahoo_tool
        return test_yahoo_tool.main()
    except Exception as e:
        print(f"✗ 运行测试失败: {e}")
        return False

def main():
    """主函数"""
    print("Yahoo Finance 工具快速开始")
    print("=" * 40)
    
    # 检查是否已安装依赖
    try:
        import yfinance
        import pandas
        import numpy
        print("✓ 依赖包已安装")
        deps_installed = True
    except ImportError:
        print("✗ 依赖包未安装")
        deps_installed = False
    
    # 安装依赖（如果需要）
    if not deps_installed:
        if not install_dependencies():
            print("请手动安装依赖: pip install -r requirements.txt")
            return False
    
    # 运行示例
    if not run_example():
        print("示例运行失败，请检查网络连接和依赖安装")
        return False
    
    # 询问是否运行测试
    print("\n" + "=" * 40)
    response = input("是否运行完整测试？(y/n): ").lower().strip()
    if response in ['y', 'yes', '是']:
        if run_test():
            print("\n🎉 所有测试通过！工具已准备就绪。")
        else:
            print("\n⚠️  部分测试失败，但基本功能可用。")
    
    print("\n工具使用说明:")
    print("1. 查看 README.md 了解详细用法")
    print("2. 运行 python integration_example.py 查看Agent集成示例")
    print("3. 运行 python test_yahoo_tool.py 进行完整测试")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
