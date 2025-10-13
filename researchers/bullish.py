# researchers/bullish.py
from __future__ import annotations
import json, asyncio
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# ===== Schema =====
class EvidenceItem(BaseModel):
    source: Literal["fundamentals","news","sentiment","market"]
    pointer: str
    note: str

class CounterItem(BaseModel):
    claim_id: str                 # id/label of the bear claim being rebutted (or "latest")
    rebuttal: str
    evidence: List[EvidenceItem]

class BullishResearch(BaseModel):
    stance: Literal["bullish"] = "bullish"
    thesis: str                   # one-sentence bullish thesis
    arguments: List[str]          # 3–5 concise bullish bullets
    counters: List[CounterItem]   # rebuttals to bear claims with evidence
    uncertainties: List[str]      # acknowledged unknowns / risks
    evidence_map: List[EvidenceItem]  # general evidence not tied to a specific counter
    language: Literal["en"] = "en"
    currency: Optional[str] = None
    market: Optional[str] = None

# ===== Helpers =====
def _first(d: Dict[str, Any], *paths, default=None):
    """Safe nested getter by dotted path, supports simple list indexes like 'items[0]'."""
    for p in paths:
        cur = d
        try:
            for token in p.split("."):
                if not token:
                    continue
                if "[" in token and token.endswith("]"):
                    k, idx = token[:-1].split("[")
                    cur = cur.get(k, [])[int(idx)]
                else:
                    cur = cur.get(token)
            if cur is not None:
                return cur
        except Exception:
            pass
    return default

def _summarize_fundamentals(f: Dict[str, Any]) -> str:
    if not f: return "(no fundamentals)"
    c, m = f.get("company", {}), f.get("metrics", {})
    return (
        f"Company: {c.get('name','?')} ({f.get('ticker','?')})\n"
        f"Exchange: {c.get('exchange','?')}  Currency: {c.get('currency','?')}\n"
        f"Metrics: MarketCap={m.get('market_cap_usd')}, EPS={m.get('eps_ttm')}, "
        f"Rev/Share={m.get('revenue_per_share_ttm')}, Debt={m.get('total_debt_usd')}, "
        f"Dividend={m.get('dividend_per_share_ttm')}"
    )

def _summarize_news(n: Dict[str, Any], max_items=6) -> str:
    if not n: return "(no news)"
    lines = [f"- [{i}] {it.get('stance','?')}: {it.get('headline','')[:120]} (src={it.get('publisher','')})"
             for i, it in enumerate((n.get("items") or [])[:max_items])]
    return f"News overall stance: {n.get('overall_stance','neutral')}\n" + "\n".join(lines)

def _summarize_sentiment(s: Optional[Dict[str, Any]]) -> str:
    if not s: return "(no sentiment)"
    return "Sentiment: " + ", ".join(f"{k}={v}" for k, v in list(s.items())[:8])

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

def _roll_history(history: Optional[List[Dict[str, str]]], max_turns=6) -> str:
    if not history: return "(no prior history)"
    rolled = history[-max_turns:]
    return "\n".join(f"{h.get('role')}: {h.get('text')}" for h in rolled)
    
def _sent_ok(s):
    if not isinstance(s, dict): return False
    if s.get("overall_sentiment") in (None, "error"): return False
    if s.get("count") == 0 or s.get("metrics", {}).get("total_tweets", 0) == 0: return False
    return True

# ===== Prompt =====
PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a **bullish equity researcher**. Your job is to build the strongest optimistic case "
     "based on the provided evidence and return **strict JSON** that matches the schema. "
     "Never change stance; it must remain 'bullish'. Output language: English."),
    ("user",
     "Ticker: {ticker}\nMarket: {market}  Currency: {currency}\n\n"
     "Fundamentals (summary):\n{fund_summary}\n\n"
     "News (summary):\n{news_summary}\n\n"
     "Sentiment (summary):\n{sent_summary}\n\n"
     "Market & Technical (summary):\n{market_summary}\n\n"
     "Recent debate history:\n{history}\n\n"
     "Latest bear argument:\n{latest_bear}\n\n"
     "JSON Schema:\n{json_schema}\n\n"
     "Return ONLY valid JSON (no extra text).")
])

# ===== Researcher =====
class BullishResearcher:
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0, timeout: int = 30, retries: int = 2):
        self.llm = ChatOpenAI(model=model, temperature=temperature, timeout=timeout)
        self.retries = retries

    async def run(
        self,
        *,
        ticker: str,
        analyst_bundle: Dict[str, Any],               # single mega JSON blob
        latest_bear: Optional[str] = None,
        debate_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:

        # Accept both shapes: {fundamentals, news, sentiment, market} or nested under channels
        fundamentals = analyst_bundle.get("fundamentals") or _first(analyst_bundle, "channels.fundamentals", default={})
        news         = analyst_bundle.get("news")         or _first(analyst_bundle, "channels.news", default={})
        sentiment    = analyst_bundle.get("sentiment")    or _first(analyst_bundle, "channels.sentiment", default=None)
        market_data  = analyst_bundle.get("market")       or _first(analyst_bundle, "channels.market", default=None)
        evidence_map_extra = []
        if _sent_ok(sentiment):
            evidence_map_extra.append({
                "source": "sentiment",
                "pointer": f"overall_sentiment={sentiment.get('overall_sentiment')}, sentiment_score={sentiment.get('sentiment_score')}",
                "note": "Aggregated social sentiment"
            })

        currency = _first(fundamentals or {}, "company.currency", default=_first(analyst_bundle, "company.currency", default="USD"))
        market   = _first(fundamentals or {}, "company.exchange", default=_first(analyst_bundle, "market", default="US"))

        # Short, readable briefs to help the LLM focus
        fund_summary = _summarize_fundamentals(fundamentals)
        news_summary = _summarize_news(news)
        sent_summary = _summarize_sentiment(sentiment)
        market_summary = _summarize_market(market_data)
        history_txt  = _roll_history(debate_history, max_turns=6)
        latest_bear  = latest_bear or "(no bear argument provided)"
        schema_hint  = json.dumps(BullishResearch.model_json_schema(), indent=2)

        messages = PROMPT.format_messages(
            ticker=ticker, market=market, currency=currency,
            fund_summary=fund_summary, news_summary=news_summary, sent_summary=sent_summary,
            market_summary=market_summary,
            history=history_txt, latest_bear=latest_bear, json_schema=schema_hint
        )

        # Call with simple retry
        last_err = None
        for _ in range(self.retries + 1):
            try:
                raw = (await self.llm.ainvoke(messages)).content
                # Extract JSON payload
                s, e = raw.find("{"), raw.rfind("}")
                candidate = raw[s:e+1] if s != -1 and e != -1 else raw
                data = json.loads(candidate)
                try:
                    obj = BullishResearch(**data)  # strict validation
                except ValidationError:
                    # best-effort coercion
                    obj = BullishResearch(
                        thesis=data.get("thesis","Secular growth and competitive moats support a bullish outlook."),
                        arguments=data.get("arguments", [])[:5],
                        counters=data.get("counters", []),
                        uncertainties=data.get("uncertainties", []),
                        evidence_map=data.get("evidence_map", []),
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

            except Exception as e:
                last_err = e
                await asyncio.sleep(0.8)
        raise last_err

# ===== LangChain tool wrapper =====
@tool("bullish_research", return_direct=False)
async def bullish_research_tool(
    ticker: str,
    analyst_bundle: Dict[str, Any],
    latest_bear: Optional[str] = None,
    debate_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Perform bullish-side research on a given stock ticker.

    Args:
        ticker: The stock ticker symbol to analyze (e.g., "AAPL").
        analyst_bundle: Pre-collected analyst data (fundamentals, news, sentiment, etc.).
        latest_bear: Optional most recent bearish stance for context in debate.
        debate_history: Optional prior debate turns for continuity.

    Returns:
        A JSON-style dict with bullish stance, supporting evidence, and rationale
        for use in debate and final decision-making.
    """
    return await BullishResearcher().run(
        ticker=ticker,
        analyst_bundle=analyst_bundle,
        latest_bear=latest_bear,
        debate_history=debate_history
    )

