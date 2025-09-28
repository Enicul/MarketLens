import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from .search import Tweet

class SentimentPatterns:
    """情绪模式匹配器"""
    
    BULLISH = re.compile(
        r'\b(bull(?:ish)?|buy(?:ing)?|long|moon(?:ing)?|pump|calls?|upgrade|breakout|support|accumula\w+|'
        r'oversold|reversal|bottom|dip\s*buy|load(?:ing)?|💎🙌|🚀+|📈+|🔥+|💰+|to\s*the\s*moon)\b|'
        r'\$\w+\s*(?:calls?|[0-9]+c)', 
        re.IGNORECASE
    )
    
    BEARISH = re.compile(
        r'\b(bear(?:ish)?|sell(?:ing)?|short|puts?|dump|crash|plunge|tank|downgrade|breakdown|resistance|'
        r'overbought|top|exit|cut\s*loss|rug\s*pull|bubble|📉+|💩+|🔴+|⚠️+)\b|'
        r'\$\w+\s*(?:puts?|[0-9]+p)',
        re.IGNORECASE
    )


@dataclass
class SentimentMetrics:
    """情绪分析指标"""
    overall_sentiment: str
    sentiment_score: float
    sentiment_breakdown: Dict[str, float]
    influence_concentration: float
    sentiment_volatility: float
    quality_score: float
    confidence_level: float


class AdvancedSentimentAnalyzer:
    """
    专业的情绪分析器
    整合了原来sentiment_analyzer.py的全部功能
    """
    
    SENTIMENT_THRESHOLDS = {
        'strong_bullish': 0.3,
        'bullish': 0.1,
        'neutral': (-0.1, 0.1),
        'bearish': -0.3,
        'strong_bearish': float('-inf')
    }
    
    def __init__(self):
        self.patterns = SentimentPatterns()
    
    def analyze(self, tweets: List[Tweet]) -> Tuple[SentimentMetrics, List[Dict[str, Any]]]:
        """核心分析方法"""
        if not tweets:
            raise ValueError("No tweets to analyze. Maybe try a stock people actually care about?")
        
        # 计算加权情绪
        weighted_sentiments = self._calculate_weighted_sentiments(tweets)
        total_influence = sum(t.engagement_score for t in tweets)
        
        # 聚合情绪分数
        weighted_sentiment = self._aggregate_sentiment_score(weighted_sentiments)
        
        # 生成指标
        metrics = self._generate_metrics(
            tweets, weighted_sentiments, weighted_sentiment, total_influence
        )
        
        # 处理推文详情
        tweet_details = self._process_top_tweets(tweets)
        
        return metrics, tweet_details
    
    def _calculate_weighted_sentiments(self, tweets: List[Tweet]) -> List[float]:
        """计算每条推文的加权情绪分数"""
        weighted_sentiments = []
        
        for tweet in tweets:
            # 影响力权重公式
            influence_weight = (
                tweet.engagement_score ** 0.5  # 平方根缓解极端值
                * (1 + len(tweet.content) / 280)  # 内容丰富度奖励
            )
            
            # 模式匹配计分
            bullish_score = len(self.patterns.BULLISH.findall(tweet.content))
            bearish_score = len(self.patterns.BEARISH.findall(tweet.content))
            
            # 归一化情绪分数
            if bullish_score + bearish_score > 0:
                sentiment_score = (bullish_score - bearish_score) / (bullish_score + bearish_score)
            else:
                sentiment_score = 0
            
            weighted_sentiments.append(sentiment_score * influence_weight)
        
        return weighted_sentiments
    
    def _aggregate_sentiment_score(self, weighted_sentiments: List[float]) -> float:
        """聚合加权情绪分数"""
        total_weight = sum(abs(s) for s in weighted_sentiments)
        return sum(weighted_sentiments) / (total_weight or 1)
    
    def _classify_sentiment(self, score: float) -> str:
        """智能情绪分类"""
        if score > self.SENTIMENT_THRESHOLDS['strong_bullish']:
            return 'strong_bullish'
        elif score > self.SENTIMENT_THRESHOLDS['bullish']:
            return 'bullish'
        elif self.SENTIMENT_THRESHOLDS['neutral'][0] <= score <= self.SENTIMENT_THRESHOLDS['neutral'][1]:
            return 'neutral'
        elif score > self.SENTIMENT_THRESHOLDS['bearish']:
            return 'bearish'
        else:
            return 'strong_bearish'
    
    def _generate_metrics(
        self, 
        tweets: List[Tweet], 
        weighted_sentiments: List[float],
        weighted_sentiment: float,
        total_influence: int
    ) -> SentimentMetrics:
        """生成高级分析指标"""
        return SentimentMetrics(
            overall_sentiment=self._classify_sentiment(weighted_sentiment),
            sentiment_score=round(weighted_sentiment, 4),
            sentiment_breakdown={
                "bullish": round(sum(1 for s in weighted_sentiments if s > 0.1) / len(tweets), 3),
                "bearish": round(sum(1 for s in weighted_sentiments if s < -0.1) / len(tweets), 3),
                "neutral": round(sum(1 for s in weighted_sentiments if -0.1 <= s <= 0.1) / len(tweets), 3)
            },
            influence_concentration=round(
                max(t.engagement_score for t in tweets) / (total_influence + 1), 3
            ),
            sentiment_volatility=round(
                (max(weighted_sentiments) - min(weighted_sentiments)) if weighted_sentiments else 0, 3
            ),
            quality_score=round(
                sum(1 for t in tweets if len(t.content) > 50 and t.engagement_score > 10) / len(tweets), 3
            ),
            confidence_level=min(1.0, len(tweets) / 50)
        )
    
    def _process_top_tweets(self, tweets: List[Tweet]) -> List[Dict[str, Any]]:
        """处理热门推文"""
        sorted_tweets = sorted(
            tweets, 
            key=lambda t: t.engagement_score ** 0.5 * (1 + len(t.content) / 280), 
            reverse=True
        )[:10]
        
        return [
            {
                "username": tweet.username,
                "content": tweet.content,
                "timestamp": tweet.timestamp,
                "influence_score": round(tweet.engagement_score ** 0.5, 2),
                "sentiment": self._classify_tweet_sentiment(tweet.content),
                "raw_metrics": {
                    "likes": tweet.likes,
                    "retweets": tweet.retweets,
                    "replies": tweet.replies
                }
            }
            for tweet in sorted_tweets
        ]
    
    def _classify_tweet_sentiment(self, content: str) -> str:
        """单条推文情绪分类"""
        has_bullish = bool(self.patterns.BULLISH.search(content))
        has_bearish = bool(self.patterns.BEARISH.search(content))
        
        if has_bullish and not has_bearish:
            return "bullish"
        elif has_bearish and not has_bullish:
            return "bearish"
        elif has_bullish and has_bearish:
            return "mixed"
        else:
            return "neutral"
