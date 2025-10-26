# adapters.py
from typing import Any, Dict

def to_research_bundle(analyst_out: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert analyze_for_manager(...) output into the 'mega JSON' both
    BullishResearcher and BearishResearcher expect.
    - Lifts analyses[...].data to top-level keys (fundamentals/news/sentiment/market)
    - Also provides a channels view for compatibility
    - Passes basic company hints (currency/exchange/name)
    - Surfaces provenance refs if present
    """
    analyses = analyst_out.get("analyses", {}) or {}
    ch = {}
    for k in ("fundamentals", "news", "sentiment", "market"):
        v = analyses.get(k)
        ch[k] = (v or {}).get("data") if isinstance(v, dict) else {}

    fundamentals = ch.get("fundamentals") or {}
    company = fundamentals.get("company") or {}

    bundle: Dict[str, Any] = {
        # flat keys
        "fundamentals": ch.get("fundamentals"),
        "news": ch.get("news"),
        "sentiment": ch.get("sentiment"),
        "market": ch.get("market"),
        # nested view
        "channels": ch,
        # helpful hints
        "company": {
            "currency": company.get("currency"),
            "exchange": company.get("exchange"),
            "name": company.get("name"),
        },
        "ticker": analyst_out.get("ticker"),
    }

    # Optional: bubble up cache/input refs for provenance
    refs = {}
    for key in ("fundamentals", "news"):
        meta = (analyses.get(key) or {}).get("meta") or {}
        input_ref = meta.get("input_ref")
        if input_ref:
            refs[key] = input_ref
    if refs:
        bundle["_refs"] = refs


    return bundle
