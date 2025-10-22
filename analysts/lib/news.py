# analysts/news.py
from __future__ import annotations
import os, re, json, hashlib, asyncio, time, logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import httpx
import feedparser
import trafilatura

from langchain_core.tools import tool
from langchain.prompts import ChatPromptTemplate

from config import LLM_GOOGLE
from dotenv import load_dotenv
load_dotenv()

# 抑制trafilatura的ERROR日志输出（这些错误不影响功能）
logging.getLogger('trafilatura').setLevel(logging.CRITICAL)




# ---------- Config ----------
FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
FMP_KEY = os.getenv("FMP_KEY", "")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_KEY", "")

# Optional fallback RSS when quotas hit (kept minimal)
RSS_SOURCES = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
]

SOURCE_TIER = {
    "Reuters": 1.3, "Wall Street Journal": 1.15, "WSJ": 1.15,
    "Yahoo Finance": 1.05, "CNBC": 1.0, "MarketWatch": 1.0,
    "finnhub": 1.05, "fmp": 1.0, "alphavantage": 1.0, "rss": 0.9
}

ALIASES = {
    "AAPL": {"aliases": ["apple", "apple inc", "iphone", "macbook"]},
    "NVDA": {"aliases": ["nvidia", "nvidia corp", "geforce", "cuda"]},
    "MSFT": {"aliases": ["microsoft", "xbox", "azure"]},
    "AMZN": {"aliases": ["amazon", "amazon.com", "aws"]},
    "GOOGL": {"aliases": ["google", "alphabet", "youtube"]},
}

# ---------- Helpers ----------
def _iso(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def _sha(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()

def resolve_ticker(q: str) -> str:
    s = q.strip().lower()
    if s.upper() in ALIASES:
        return s.upper()
    for t, rec in ALIASES.items():
        if s == t.lower() or s in rec["aliases"]:
            return t
    return q.upper()

def clean_html_to_text(html_or_text: str) -> str:
    extracted = trafilatura.extract(html_or_text, include_comments=False)
    txt = extracted or html_or_text
    return re.sub(r"\s+", " ", txt).strip()

def dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set(); out = []
    for it in sorted(items, key=lambda x: x.get("published_at",""), reverse=True):
        key = (it.get("headline","")[:150].lower(), (it.get("publisher") or "").lower())
        if key in seen: continue
        seen.add(key); out.append(it)
    return out

# ---------- Fetchers (3 APIs + fallback RSS) ----------
async def fetch_finnhub(ticker: str, lookback_hours: int = 24) -> List[Dict[str, Any]]:
    if not FINNHUB_KEY: return []
    to = datetime.now(timezone.utc).date().isoformat()
    fr = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).date().isoformat()
    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from={fr}&to={to}&token={FINNHUB_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
    out = []
    for it in data:
        title = it.get("headline") or ""
        if not title: continue
        ts = it.get("datetime", None)
        published = _iso(datetime.fromtimestamp(ts, tz=timezone.utc)) if ts else _iso()
        out.append({
            "id": _sha(it.get("url") or title),
            "url": it.get("url",""),
            "headline": title,
            "publisher": it.get("source","finnhub"),
            "published_at": published,
            "text": it.get("summary") or title
        })
    return out

async def fetch_fmp(ticker: str, lookback_hours: int = 24) -> List[Dict[str, Any]]:
    if not FMP_KEY: return []
    url = f"https://financialmodelingprep.com/api/v3/stock_news?tickers={ticker}&limit=50&apikey={FMP_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
    out = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    for it in data:
        title = it.get("title") or ""
        if not title: continue
        # FMP publishedDate example: '2025-09-20 08:31:00'
        raw = it.get("publishedDate") or ""
        try:
            published = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            published = datetime.now(timezone.utc)
        if published < cutoff: continue
        out.append({
            "id": _sha(it.get("url") or title),
            "url": it.get("url",""),
            "headline": title,
            "publisher": it.get("site","fmp"),
            "published_at": _iso(published),
            "text": clean_html_to_text(it.get("text") or title)
        })
    return out

async def fetch_alphavantage(ticker: str, lookback_hours: int = 24) -> List[Dict[str, Any]]:
    if not ALPHAVANTAGE_KEY: return []
    # NOTE: AV free tier is very rate-limited. We call once per request and filter client-side.
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={ALPHAVANTAGE_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, timeout=12)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return []
    out = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    for it in data.get("feed", []):
        title = it.get("title") or ""
        if not title: continue
        # AV time_published like '20250920T083000'
        raw = it.get("time_published","")
        try:
            published = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except Exception:
            published = datetime.now(timezone.utc)
        if published < cutoff: continue
        url0 = (it.get("url") or "") or (it.get("source_domain") or "")
        summary = it.get("summary") or it.get("excerpt") or title
        out.append({
            "id": _sha(url0 or title),
            "url": url0,
            "headline": title,
            "publisher": it.get("source","alphavantage"),
            "published_at": _iso(published),
            "text": clean_html_to_text(summary)
        })
    return out

async def fetch_rss_fallback(lookback_hours: int = 24) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc); results=[]
    for url in RSS_SOURCES:
        try:
            d = feedparser.parse(url)
        except Exception:
            continue
        for e in d.entries[:30]:
            title = e.get("title",""); link = e.get("link","")
            if not title: continue
            published = (_iso() if not e.get("published_parsed")
                         else datetime(*e.published_parsed[:6], tzinfo=timezone.utc).isoformat())
            try:
                ts = datetime.fromisoformat(published.replace("Z","+00:00"))
                if (now - ts) > timedelta(hours=lookback_hours): continue
            except Exception:
                pass
            publisher = (e.get("source",{}).get("title") or d.feed.get("title") or "rss")
            summary = clean_html_to_text(e.get("summary","") or "")
            results.append({
                "id": _sha(link or title),
                "url": link,
                "headline": title,
                "publisher": publisher,
                "published_at": published,
                "text": summary or title
            })
    return results

# ---------- LLM summarizer ----------
_llm = LLM_GOOGLE



_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a financial news analyst. Your task is to read news headlines and short text "
     "about a stock and classify the market stance as clearly bullish, bearish, neutral, or mixed. "
     "Do not hedge — pick the stance that best reflects investor sentiment."),
    ("user",
     "Analyze the following news for ticker {ticker}.\n\n"
     "Headline: {headline}\nPublisher: {publisher}\nDate: {date}\nText: {text}\n\n"
     "Return JSON ONLY with these keys:\n"
     "summary: 2-3 concise factual bullets\n"
     "stance: one of 'bullish', 'bearish', 'neutral', 'mixed'\n"
     "rationale: a one-sentence explanation of why this stance was chosen\n\n"
     "Examples:\n"
     "{{\n"
     "  \"summary\": [\"Company raises revenue guidance for FY2025\", \"New product launch well received\"],\n"
     "  \"stance\": \"bullish\",\n"
     "  \"rationale\": \"Raised guidance and positive product launch suggest improving outlook\"\n"
     "}}\n\n"
     "{{\n"
     "  \"summary\": [\"Company warns of supply chain issues\", \"Cuts Q3 earnings forecast\"],\n"
     "  \"stance\": \"bearish\",\n"
     "  \"rationale\": \"Lower guidance and negative forecast indicate weaker outlook\"\n"
     "}}\n")
])



async def summarize_item(item: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    msgs = _prompt.format_messages(
        ticker=ticker,
        headline=item["headline"],
        publisher=item.get("publisher") or "unknown",
        date=item.get("published_at") or _iso(),
        text=(item.get("text") or item.get("headline"))[:3000]
    )

    try:
        resp = await _llm.ainvoke(msgs)
        j = json.loads(resp.content)
        stance = j.get("stance","neutral")
        summary = j.get("summary",[item["headline"]])
    except Exception:
        stance = "neutral"; summary = [item["headline"]]
    return {
        "type": "news_item",
        "ticker": [ticker],
        "publisher": item.get("publisher"),
        "published_at": item.get("published_at"),
        "headline": item.get("headline"),
        "evidence": [item.get("url")] if item.get("url") else [],
        "summary": summary,
        "stance": stance,
        "stance_confidence": 0.6 if stance in ("bullish","bearish") else 0.5,
        "signals": [],
        "finbert": None
    }

# ---------- Orchestrator ----------
async def gather_and_summarize(ticker: str, top_k: int = 8, lookback_hours: int = 24) -> Dict[str, Any]:
    # Fetch all three APIs in parallel; fallback to RSS if nothing comes back
    finnhub_coro = fetch_finnhub(ticker, lookback_hours)
    fmp_coro = fetch_fmp(ticker, lookback_hours)
    av_coro = fetch_alphavantage(ticker, lookback_hours)

    finnhub, fmp, av = await asyncio.gather(finnhub_coro, fmp_coro, av_coro)
    items = finnhub + fmp + av
    if not items:  # quotas or outages → try basic RSS
        items = await fetch_rss_fallback(lookback_hours)

    # Dedupe & rank by source tier (simple heuristic)
    items = dedupe(items)
    def _rank(it):
        return SOURCE_TIER.get((it.get("publisher") or "").strip(), 1.0)
    items = sorted(items, key=_rank, reverse=True)[:max(1, top_k)]

    # Summarize in parallel
    summaries = await asyncio.gather(*[summarize_item(it, ticker) for it in items])

    # Majority vote stance
    bulls = sum(1 for x in summaries if x["stance"] == "bullish")
    bears = sum(1 for x in summaries if x["stance"] == "bearish")
    overall = "bullish" if bulls > bears else ("bearish" if bears > bulls else "neutral")

    return {
        "ticker": ticker,
        "channel": "news",
        "overall_stance": overall,
        "count": len(summaries),
        "items": summaries,
        "generated_at": _iso()
    }

# ---------- LangChain Tool ----------

@tool("get_news", return_direct=False)
async def get_news(ticker: str) -> dict:
    """
    Fetch and summarize recent financial news for the given ticker or company name
    using Finnhub, FMP, and Alpha Vantage (free tiers). Falls back to RSS if quotas hit.
    Returns JSON with overall_stance and per-item bullets/stance.
    """
    t = resolve_ticker(ticker)
    return await gather_and_summarize(t)
