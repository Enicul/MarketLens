import os
import logging
import httpx
import datetime
import asyncio
from typing import Dict, Any
from langchain.tools import StructuredTool
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
FMP_KEY = os.getenv("FMP_KEY", "")

BASE_FMP = "https://financialmodelingprep.com/api/v3"
BASE_FINNHUB = "https://finnhub.io/api/v1"


# -------- Helpers --------
def _prune_nones(obj):
    """Recursively drop None/empty values from dicts and lists."""
    if isinstance(obj, dict):
        return {
            k: _prune_nones(v)
            for k, v in obj.items()
            if v not in (None, "", [], {}, float("nan"))
        }
    if isinstance(obj, list):
        return [
            _prune_nones(v)
            for v in obj
            if v not in (None, "", [], {}, float("nan"))
        ]
    return obj


# -------- FMP Fetchers --------
async def fetch_fmp_profile(ticker: str) -> Dict[str, Any]:
    url = f"{BASE_FMP}/profile/{ticker}?apikey={FMP_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return {}


async def fetch_fmp_metrics(ticker: str) -> Dict[str, Any]:
    url = f"{BASE_FMP}/key-metrics/{ticker}?limit=1&apikey={FMP_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return {}


# -------- Finnhub Fallback --------
async def fetch_profile_and_metrics(ticker: str):
    profile, metrics = await asyncio.gather(
        fetch_fmp_profile(ticker),
        fetch_fmp_metrics(ticker),
    )

    if not profile or not metrics:
        async with httpx.AsyncClient() as client:
            r1 = await client.get(
                f"{BASE_FINNHUB}/stock/profile2?symbol={ticker}&token={FINNHUB_KEY}"
            )
            r2 = await client.get(
                f"{BASE_FINNHUB}/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_KEY}"
            )
            profile = r1.json() or {}
            metrics = r2.json().get("metric", {}) if r2.json() else {}

    return profile, metrics


# -------- Insiders --------
async def fetch_insiders(ticker: str) -> Any:
    url = f"{BASE_FINNHUB}/stock/insider-transactions?symbol={ticker}&token={FINNHUB_KEY}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.json().get("data", [])


# -------- Main Aggregator --------
async def get_fundamentals_func(ticker: str) -> Dict[str, Any]:
    logger.info(f"[FUNDAMENTALS] 📊 Fetching fundamentals: {ticker}")
    try:
        profile, metrics = await fetch_profile_and_metrics(ticker)
        logger.debug(f"[FUNDAMENTALS] 📥 Profile and metrics retrieved: {ticker}")
        insiders = await fetch_insiders(ticker)
        logger.debug(f"[FUNDAMENTALS] 👥 Insider transaction data retrieved: {ticker}")
    except Exception as e:
        logger.error(f"[FUNDAMENTALS] ❌ Failed to pull data for {ticker}: {e}")
        raise

    # --- Normalize company info ---
    company = {
        "name": profile.get("companyName") or profile.get("name"),
        "exchange": (profile.get("exchange") or "").split(" - ")[0]
        or profile.get("exchange"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "country": profile.get("country") or profile.get("countryCode"),
        "currency": profile.get("currency"),
        "ceo": profile.get("ceo") or profile.get("CEO"),
        "website": profile.get("website"),
    }

    # --- Normalize metrics ---
    m = metrics or {}
    mc = m.get("marketCapTTM") or m.get("marketCapitalization")
    try:
        if mc and "marketCapitalization" in m and "marketCapTTM" not in m:
            mc = float(mc) * 1_000_000.0  # Finnhub millions → USD
    except Exception:
        pass

    metrics_norm = {
        "market_cap_usd": mc if isinstance(mc, (int, float)) else None,
        "revenue_per_share_ttm": m.get("revenuePerShareTTM")
        or m.get("revenuePerShare"),
        "eps_ttm": m.get("netIncomePerShareTTM") or m.get("eps"),
        "total_debt_usd": m.get("totalDebtTTM") or m.get("totalDebt"),
        "dividend_per_share_ttm": m.get("dividendPerShareTTM")
        or m.get("dividendPerShare"),
    }

    # --- Normalize insiders (last 5) ---
    insiders_compact = [
        {
            "person": it.get("name"),
            "code": it.get("transactionCode"),
            "date": it.get("transactionDate"),
            "price": it.get("transactionPrice"),
            "change_shares": it.get("change"),
            "post_shares": it.get("share"),
            "filing_id": it.get("id"),
            "source": it.get("source"),
        }
        for it in (insiders or [])
    ][:5]

    result = {
        "ticker": ticker,
        "company": company,
        "metrics": metrics_norm,
        "insiders": insiders_compact,
        "retrieved_at": datetime.datetime.utcnow().isoformat(),
    }

    logger.info(f"[FUNDAMENTALS] ✅ Fundamentals normalized: {ticker}")
    return _prune_nones(result)


# -------- LangChain Tool Wrapper --------




get_fundamentals = StructuredTool.from_function(
    func=get_fundamentals_func,
    coroutine=get_fundamentals_func,   # ✅ tell LangChain this is async
    name="get_fundamentals",
    description=(
        "Get lean company fundamentals (profile, key financial metrics, "
        "and recent insider transactions) for a given stock ticker. "
        "Only includes fields available from free APIs."
    ),
)
