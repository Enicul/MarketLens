# researchers/bearish_bundle.py
from __future__ import annotations
import json, asyncio
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError
from config import LLM_GOOGLE
from langchain.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# -------- schema  --------
class EvidenceItem(BaseModel):
    source: Literal["fundamentals","news","sentiment","market"]
    pointer: str
    note: str

class CounterItem(BaseModel):
    claim_id: str
    rebuttal: str
    evidence: List[EvidenceItem]

class BearishResearch(BaseModel):
    stance: Literal["bearish"] = "bearish"
    thesis: str
    arguments: List[str]
    counters: List[CounterItem]
    uncertainties: List[str]
    evidence_map: List[EvidenceItem]
    language: Literal["en"] = "en"
    currency: Optional[str] = None
    market: Optional[str] = None

# -------- small helpers --------
def _first(d: Dict[str,Any], *paths, default=None):
    for p in paths:
        cur = d
        try:
            for k in p.split("."):
                if k.endswith("]"):
                    k, idx = k[:-1].split("["); cur = cur.get(k, [])[int(idx)]
                else:
                    cur = cur.get(k)
            if cur is not None: return cur
        except Exception:
            pass
    return default

def _summarize_fundamentals(f: Dict[str,Any]) -> str:
    if not f: return "(no fundamentals)"
    c, m = f.get("company",{}), f.get("metrics",{})
    return (
        f"Company: {c.get('name','?')} ({f.get('ticker','?')})\n"
        f"Exchange: {c.get('exchange','?')}  Currency: {c.get('currency','?')}\n"
        f"Metrics: MarketCap={m.get('market_cap_usd')}, EPS={m.get('eps_ttm')}, "
        f"Rev/Share={m.get('revenue_per_share_ttm')}, Debt={m.get('total_debt_usd')}, "
        f"Dividend={m.get('dividend_per_share_ttm')}"
    )

def _summarize_news(n: Dict[str,Any], max_items=6) -> str:
    if not n: return "(no news)"
    items = n.get("items", [])[:max_items]
    rows = [f"- [{i}] {it.get('stance','?')}: {it.get('headline','')[:120]} (src={it.get('publisher','')})"
            for i,it in enumerate(items)]
    return f"News overall stance: {n.get('overall_stance','neutral')}\n" + "\n".join(rows)

def _summarize_sentiment(s: Optional[Dict[str,Any]]) -> str:
    if not s: return "(no sentiment)"
    return "Sentiment: " + ", ".join(f"{k}={v}" for k,v in list(s.items())[:8])

def _summarize_market(m: Optional[Dict[str, Any]]) -> str:
    if not m: return "(no market data)"
    stock_info = m.get("stock_basic_info", {})
    tech_ind = m.get("technical_indicators", {})
    price_analysis = m.get("price_analysis", {})
    
    lines = []
    if stock_info:
        lines.append(f"Current: ${stock_info.get('current_price')} ({stock_info.get('change_percent'):+.2f}%)")
        lines.append(f"52w: ${stock_info.get('low_52w')} - ${stock_info.get('high_52w')}")
    
    if tech_ind:
        mas = tech_ind.get("moving_averages", {})
        osc = tech_ind.get("oscillators", {})
        if mas:
            lines.append(f"MA: {', '.join(f'{k}={v:.2f}' for k,v in list(mas.items())[:3])}")
        if osc and osc.get("rsi"):
            lines.append(f"RSI: {osc.get('rsi'):.1f}")
    
    return "Market Data:\n" + "\n".join(lines) if lines else "(no market data)"

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a bearish equity researcher. Produce a **strict JSON** per schema. "
     "Never change stance; it must remain 'bearish'. Output language: English."),
    ("user",
     "Ticker: {ticker}\nMarket: {market}  Currency: {currency}\n\n"
     "Fundamentals (summary):\n{fund_summary}\n\n"
     "News (summary):\n{news_summary}\n\n"
     "Sentiment (summary):\n{sent_summary}\n\n"
     "Market & Technical (summary):\n{market_summary}\n\n"
     "Recent debate history:\n{history}\n\n"
     "Latest bull argument:\n{latest_bull}\n\n"
     "JSON Schema:\n{json_schema}\n\n"
     "Return ONLY valid JSON.")
])

def _sent_ok(s):
    if not isinstance(s, dict): return False
    if s.get("overall_sentiment") in (None, "error"): return False
    if s.get("count") == 0 or s.get("metrics", {}).get("total_tweets", 0) == 0: return False
    return True


class BearishResearcher:
    def __init__(self, temperature=0, timeout=30):
        self.llm = LLM_GOOGLE

    async def run(
        self,
        *,
        ticker: str,
        analyst_bundle: Dict[str,Any],          # << single mega JSON
        latest_bull: Optional[str] = None,
        debate_history: Optional[List[Dict[str,str]]] = None
    ) -> Dict[str,Any]:

        # --- auto-detect sections from bundle (works for both old & new shapes)
        fundamentals = analyst_bundle.get("fundamentals") or _first(analyst_bundle, "channels.fundamentals", default={})
        news         = analyst_bundle.get("news")         or _first(analyst_bundle, "channels.news", "news_pack", default={})
        sentiment    = analyst_bundle.get("sentiment")    or _first(analyst_bundle, "channels.sentiment", default=None)
        market_data  = analyst_bundle.get("market")       or _first(analyst_bundle, "channels.market", default=None)
        evidence_map_extra = []
        if _sent_ok(sentiment):
            evidence_map_extra.append({
                "source": "sentiment",
                "pointer": f"overall_sentiment={sentiment.get('overall_sentiment')}, sentiment_score={sentiment.get('sentiment_score')}",
                "note": "Aggregated social sentiment"
            })


        # --- default market/currency from fundamentals if present
        currency = _first(fundamentals or {}, "company.currency", default=_first(analyst_bundle, "company.currency"))
        market   = _first(fundamentals or {}, "company.exchange", default=_first(analyst_bundle, "market"))

        fund_summary = _summarize_fundamentals(fundamentals)
        news_summary = _summarize_news(news)
        sent_summary = _summarize_sentiment(sentiment)
        market_summary = _summarize_market(market_data)
        history_txt  = "\n".join(f"{h.get('role')}: {h.get('text')}" for h in (debate_history or [])[-6:]) or "(no history)"
        latest_bull  = latest_bull or "(no bull argument provided)"
        schema_hint  = json.dumps(BearishResearch.model_json_schema(), indent=2)

        msgs = PROMPT.format_messages(
            ticker=ticker, market=market or "Unknown", currency=currency or "USD",
            fund_summary=fund_summary, news_summary=news_summary, sent_summary=sent_summary,
            market_summary=market_summary,
            history=history_txt, latest_bull=latest_bull, json_schema=schema_hint
        )

        raw = (await self.llm.ainvoke(msgs)).content
        # extract JSON
        try:
            j = json.loads(raw[raw.find("{"): raw.rfind("}")+1])
        except Exception:
            j = {}

        # validate / coerce
        try:
            obj = BearishResearch(**j)
        except ValidationError:
            obj = BearishResearch(
                thesis=j.get("thesis","Macro and company risks suggest a bearish outlook."),
                arguments=j.get("arguments",[])[:5],
                counters=j.get("counters",[]),
                uncertainties=j.get("uncertainties",[]),
                evidence_map=j.get("evidence_map",[]),
                currency=currency, market=market
            )

        out = obj.model_dump()

        # attach sentiment evidence if valid
        if _sent_ok(sentiment):
            out["evidence_map"].append({
                "source": "sentiment",
                "pointer": f"overall_sentiment={sentiment.get('overall_sentiment')}, sentiment_score={sentiment.get('sentiment_score')}",
                "note": "Aggregated social sentiment"
            })

        out.update({
            "ticker": ticker,
            "input_refs": {
                "fundamentals_ref": (fundamentals or {}).get("retrieved_at"),
                "news_ref": (news or {}).get("generated_at"),
            },
            "meta": {"model": "gpt-4o-mini", "language": "en"}
        })
        return out

        


# optional LangChain tool wrapper
@tool("bearish_research", return_direct=False)
async def bearish_research_tool(
    ticker: str,
    analyst_bundle: Dict[str, Any],
    latest_bull: Optional[str] = None,
    debate_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Perform bearish-side research on a given stock ticker.

    Args:
        ticker: The stock ticker symbol to analyze (e.g., "AAPL").
        analyst_bundle: Pre-collected analyst data (fundamentals, news, sentiment, etc.).
        latest_bull: Optional most recent bullish stance for context in debate.
        debate_history: Optional prior debate turns for continuity.

    Returns:
        A JSON-style dict with bearish stance, supporting evidence, and rationale
        for use in debate and final decision-making.
    """
    return await BearishResearcher().run(
        ticker=ticker,
        analyst_bundle=analyst_bundle,
        latest_bull=latest_bull,
        debate_history=debate_history
    )
