#!/usr/bin/env python3
"""
推特股票信息爬虫 - 简化使用脚本
"""
import asyncio
import sys
from datetime import datetime
from search import TwitterStockScraper
from config import Config

async def scrape_single_stock(stock_symbol: str, max_tweets: int = 20):
    """爬取单个股票的推文"""
    print(f"🚀 开始爬取 {stock_symbol} 的推文...")
    
    async with TwitterStockScraper(headless=False) as scraper:
        tweets = await scraper.search_stock_tweets(stock_symbol, max_tweets)
        
        if tweets:
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            json_file = f"{stock_symbol}_tweets_{timestamp}.json"
            csv_file = f"{stock_symbol}_tweets_{timestamp}.csv"
            
            # 保存数据
            await scraper.save_to_json(tweets, json_file)
            await scraper.save_to_csv(tweets, csv_file)
            
            # 显示统计信息
            print(f"✅ {stock_symbol} 爬取完成!")
            print(f"   📊 推文数量: {len(tweets)}")
            print(f"   💾 已保存到: {json_file}, {csv_file}")
            
            # 显示前几条推文预览
            print(f"\n📝 推文预览:")
            for i, tweet in enumerate(tweets[:3], 1):
                print(f"   {i}. @{tweet['username']}: {tweet['content'][:100]}...")
                print(f"      �� {tweet['likes']} | 🔄 {tweet['retweets']} | 💬 {tweet['replies']}")
        else:
            print(f"❌ 未找到 {stock_symbol} 的相关推文")

async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python run_scraper.py <股票代码> [推文数量]")
        print("示例: python run_scraper.py AAPL 30")
        print(f"支持的股票: {', '.join(Config.STOCK_SYMBOLS)}")
        return
    
    stock_symbol = sys.argv[1].upper()
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    # if stock_symbol not in Config.STOCK_SYMBOLS:
    #     print(f"⚠️  警告: {stock_symbol} 不在预定义列表中")
    #     print(f"支持的股票: {', '.join(Config.STOCK_SYMBOLS)}")
    
    await scrape_single_stock(stock_symbol, max_tweets)

if __name__ == "__main__":
    asyncio.run(main())
