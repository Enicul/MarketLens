# researchers/debate.py
from __future__ import annotations
import json, asyncio
from typing import Any, Dict, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, ValidationError
from config import LLM_GOOGLE_FLASH
from langchain.prompts import ChatPromptTemplate
from langchain_core.tools import tool

# ========= Shared schema bits =========
class EvidenceItem(BaseModel):
    source: Literal["fundamentals","news","sentiment","market"]
    pointer: str
    note: str

class SidePack(BaseModel):
    stance: Literal["bullish","bearish"]
    thesis: str
    arguments: List[str]
    counters: List[Dict[str, Any]]          # passthrough from side tools
    uncertainties: List[str]
    evidence_map: List[EvidenceItem]
    language: Literal["en"]
    currency: Optional[str] = None
    market: Optional[str] = None
    ticker: Optional[str] = None

# ========= Final moderator output =========
class DecisionAction(BaseModel):
    recommendation: Literal["BUY","SELL","HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    time_horizon: Literal["short","medium","long"]
    triggers_up: List[str]                  # objective milestones to raise conviction / move to BUY
    triggers_down: List[str]                # objective milestones to lower conviction / move to SELL

class DecisionPack(BaseModel):
    ticker: str
    stance_summary: Dict[str, str]          # {"bullish_thesis": "...", "bearish_thesis": "..."}
    consensus: List[str]
    disagreements: List[Dict[str, str]]     # {topic, bull_view, bear_view}
    key_upside: List[str]
    key_risks: List[str]
    scorecard: Dict[str, float]             # {"bull_strength": x, "bear_strength": y, "uncertainty": z, "net_score": x-y-z}
    action: DecisionAction
    rationale: str
    evidence_citations: List[EvidenceItem]
    meta: Dict[str, Any]


# ========= Prompt =========
PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are the Market Lens debate moderator, consolidating bullish and bearish briefs into a decision memo for the investment committee.\n"
     "Operating standards:\n"
     "- Remain neutral and audit-ready; reconcile conflicts with explicit references to provided evidence only.\n"
     "- Weight arguments by evidence quality and freshness; flag unsupported claims rather than amplifying them.\n"
     "- Ensure the action plan respects the stated risk_tolerance and time_horizon.\n"
     "- Deliver strict JSON that conforms to the schema; narrative fields must stay in English."),
    ("user",
     "Ticker: {ticker}\n"
     "Risk tolerance: {risk_tolerance}\n"
     "Default horizon: {time_horizon}\n\n"
     "Bullish JSON:\n{bull_json}\n\n"
     "Bearish JSON:\n{bear_json}\n\n"
     "JSON Schema (target output):\n{schema}\n\n"
     "Instructions:\n"
     "1) Summarize both theses.\n"
     "2) Extract consensus facts (both sides implicitly/explicitly accept).\n"
     "3) List disagreements as {{topic, bull_view, bear_view}}.\n"
     "4) Distill key upside and key risks (use strongest, well-evidenced points).\n"
     "5) Build a scorecard: bull_strength, bear_strength (0–1), uncertainty (0–1), net_score = bull-bear-uncertainty.\n"
     "6) Map net_score to a recommendation (BUY if > +0.15, SELL if < -0.15, else HOLD); adjust by risk_tolerance and time_horizon.\n"
     "7) Provide triggers_up / triggers_down (objective milestones that would change the call).\n"
     "8) Include evidence_citations as a deduped list from both sides' evidence.\n"
     "Quality checks:\n"
     "- If evidence is insufficient for a field, include a concise explanation while keeping the schema intact.\n"
     "- Return ONLY valid JSON; no surrounding text.")
])

# ========= Helpers: normalization / scoring / provenance =========
_CANON_PTR = {
    "MarketCap": "metrics.market_cap_usd",
    "MarketCapTTM": "metrics.market_cap_usd",
    "Rev/Share": "metrics.revenue_per_share_ttm",
    "RevenuePerShareTTM": "metrics.revenue_per_share_ttm",
    "Dividend": "metrics.dividend_per_share_ttm",
    "DividendPerShareTTM": "metrics.dividend_per_share_ttm",
    "EPS": "metrics.eps_ttm",
    "EPS_TTM": "metrics.eps_ttm",
}

def _canon_pointer(ptr: str) -> str:
    if not isinstance(ptr, str):
        return str(ptr)
    if "=" in ptr:                    # e.g., "MarketCap=3786..."
        ptr = ptr.split("=", 1)[0].strip()
    return _CANON_PTR.get(ptr, ptr)

def _normalize_stance_summary(out: dict, bull_thesis: str, bear_thesis: str) -> None:
    ss = out.get("stance_summary", {}) or {}
    out["stance_summary"] = {
        "bullish_thesis": ss.get("bullish_thesis") or ss.get("bullish") or bull_thesis,
        "bearish_thesis": ss.get("bearish_thesis") or ss.get("bearish") or bear_thesis,
    }

def _inject_news_citations_if_missing(out: dict, bull: dict, bear: dict) -> None:
    cites = out.get("evidence_citations", []) or []
    has_news = any(c.get("source") == "news" for c in cites)
    if has_news:
        return
    for side in (bull, bear):
        for ev in side.get("evidence_map", []):
            if ev.get("source") == "news":
                cites.append({"source": "news", "pointer": ev.get("pointer","items[0].headline"), "note": ev.get("note","")})
                if sum(1 for c in cites if c.get("source") == "news") >= 2:
                    break
        if any(c.get("source") == "news" for c in cites):
            break
    out["evidence_citations"] = cites

def _canon_and_dedupe_citations(out: dict) -> None:
    cites = out.get("evidence_citations", []) or []
    seen = set(); normed = []
    for c in cites:
        src = c.get("source")
        ptr = _canon_pointer(c.get("pointer",""))
        key = (src, ptr)
        if key in seen:
            continue
        seen.add(key)
        normed.append({"source": src, "pointer": ptr, "note": c.get("note","")})
    out["evidence_citations"] = normed

def _move_eps_missing_to_uncertainty(out: dict) -> None:
    cites = out.get("evidence_citations", []) or []
    bad = [c for c in cites if "eps" in str(c.get("pointer","")).lower() and ("none" in str(c.get("pointer","")).lower())]
    if bad:
        out.setdefault("key_risks", []).append("Earnings visibility/data gap: EPS TTM missing in source feed.")
        out["evidence_citations"] = [c for c in cites if c not in bad]

def _attach_input_refs(out: dict, bull: dict, bear: dict) -> None:
    br = (bull.get("input_refs") or {})
    ar = (bear.get("input_refs") or {})
    out.setdefault("meta", {})
    out["meta"]["input_refs"] = {
        "fundamentals_ref": br.get("fundamentals_ref") or ar.get("fundamentals_ref"),
        "news_ref": br.get("news_ref") or ar.get("news_ref"),
    }

def _clamp(v: float, lo: float, hi: float) -> float:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return max(lo, min(hi, v))

def _recompute_scorecard(score: Dict[str, float]) -> Dict[str, float]:
    b = _clamp(score.get("bull_strength", 0.5), 0.0, 1.0)
    r = _clamp(score.get("bear_strength", 0.5), 0.0, 1.0)
    u = _clamp(score.get("uncertainty", 0.3), 0.0, 1.0)
    net = _clamp(b - r - u, -1.0, 1.0)
    return {"bull_strength": b, "bear_strength": r, "uncertainty": u, "net_score": net}

def _map_recommendation(net_score: float, risk: str, horizon: str) -> Tuple[str, float]:
    # base mapping
    if net_score > 0.15:
        rec = "BUY"
    elif net_score < -0.15:
        rec = "SELL"
    else:
        rec = "HOLD"
    # baseline confidence from |net|
    conf = _clamp(abs(net_score) + 0.35, 0.0, 0.95)
    # risk tolerance adjustment (light touch)
    if risk == "low" and rec != "HOLD":
        conf = _clamp(conf - 0.05, 0.0, 0.95)
    if risk == "high" and rec != "HOLD":
        conf = _clamp(conf + 0.05, 0.0, 0.95)
    return rec, conf

def _ensure_measurable_triggers(trigs: List[str], fallback: List[str]) -> List[str]:
    out = []
    for t in trigs or []:
        t = t.strip()
        if not t:
            continue
        # truncate and keep short, objective phrasing
        if len(t) > 140:
            t = t[:137] + "..."
        out.append(t)
        if len(out) >= 3:
            break
    if not out:
        out = fallback[:3]
    return out

# ========= Moderator =========
class DebateModerator:
    def __init__(self, temperature: float = 0, timeout: int = 40, retries: int = 2):
        self.llm = LLM_GOOGLE_FLASH
        self.retries = retries

    @staticmethod
    def _coerce_side(side: Dict[str, Any], expected: Literal["bullish","bearish"]) -> SidePack:
        base = {
            "stance": side.get("stance", expected),
            "thesis": side.get("thesis", f"No {expected} thesis provided."),
            "arguments": side.get("arguments", []),
            "counters": side.get("counters", []),
            "uncertainties": side.get("uncertainties", []),
            "evidence_map": side.get("evidence_map", []),
            "language": side.get("language", "en"),
            "currency": side.get("currency"),
            "market": side.get("market"),
            "ticker": side.get("ticker"),
        }
        return SidePack(**base)

    async def run(
        self,
        *,
        ticker: str,
        bullish: Dict[str, Any],
        bearish: Dict[str, Any],
        risk_tolerance: Literal["low","medium","high"] = "medium",
        time_horizon: Literal["short","medium","long"] = "medium"
    ) -> Dict[str, Any]:

        bull = self._coerce_side(bullish, "bullish")
        bear = self._coerce_side(bearish, "bearish")

        schema_json = json.dumps(DecisionPack.model_json_schema(), indent=2)
        messages = PROMPT.format_messages(
            ticker=ticker,
            risk_tolerance=risk_tolerance,
            time_horizon=time_horizon,
            bull_json=json.dumps(bull.model_dump(), indent=2),
            bear_json=json.dumps(bear.model_dump(), indent=2),
            schema=schema_json
        )

        # Simple retry loop
        last_err = None
        for _ in range(self.retries + 1):
            try:
                raw = (await self.llm.ainvoke(messages)).content
                s, e = raw.find("{"), raw.rfind("}")
                candidate = raw[s:e+1] if s != -1 and e != -1 else raw
                data = json.loads(candidate)
                try:
                    obj = DecisionPack(**data)  # strict validation
                except ValidationError:
                    # Best-effort fixups if the model drifts slightly
                    data.setdefault("ticker", ticker)
                    data.setdefault("stance_summary", {
                        "bullish_thesis": bull.thesis,
                        "bearish_thesis": bear.thesis
                    })
                    data.setdefault("consensus", [])
                    data.setdefault("disagreements", [])
                    data.setdefault("key_upside", [])
                    data.setdefault("key_risks", [])
                    data.setdefault("scorecard", {"bull_strength": 0.5, "bear_strength": 0.5, "uncertainty": 0.3, "net_score": -0.3})
                    data.setdefault("action", {
                        "recommendation": "HOLD", "confidence": 0.5,
                        "time_horizon": time_horizon,
                        "triggers_up": [], "triggers_down": []
                    })
                    data.setdefault("rationale", "Model fallback synthesis.")
                    data.setdefault("evidence_citations", [])
                    data.setdefault("meta", {})
                    obj = DecisionPack(**data)

                out = obj.model_dump()

                # Normalize stance keys
                _normalize_stance_summary(out, bull.thesis, bear.thesis)

                # Citations: inject news if missing, canonicalize, dedupe, move EPS-missing to uncertainty
                _inject_news_citations_if_missing(out, bull.model_dump(), bear.model_dump())
                _canon_and_dedupe_citations(out)
                _move_eps_missing_to_uncertainty(out)

                # Provenance
                _attach_input_refs(out, bullish, bearish)

                # Score & recommendation normalization
                out["scorecard"] = _recompute_scorecard(out.get("scorecard", {}))
                rec, conf = _map_recommendation(out["scorecard"]["net_score"], risk_tolerance, time_horizon)
                action = out.get("action", {})
                out["action"] = {
                    "recommendation": action.get("recommendation", rec),
                    "confidence": _clamp(action.get("confidence", conf), 0.0, 1.0),
                    "time_horizon": action.get("time_horizon", time_horizon),
                    "triggers_up": _ensure_measurable_triggers(
                        action.get("triggers_up", []),
                        ["EPS TTM grows ≥ 10% YoY", "Gross margin expands ≥ 150 bps QoQ", "Services revenue grows ≥ 12% YoY"]
                    ),
                    "triggers_down": _ensure_measurable_triggers(
                        action.get("triggers_down", []),
                        ["EPS TTM declines ≥ 5% YoY", "China units decline ≥ 8% YoY", "Adverse ruling on platform take rate"]
                    ),
                }

                # Meta
                out.setdefault("meta", {})
                out["meta"].update({
                    "model": "gemini-2.5-pro",
                    "risk_tolerance": risk_tolerance,
                    "time_horizon": time_horizon
                })

                # Ensure ticker present
                out["ticker"] = ticker

                return out
            except Exception as e:
                last_err = e
                await asyncio.sleep(0.8)
        raise last_err

# ========= LangChain tool wrapper =========
@tool("moderate_debate", return_direct=False)
async def moderate_debate_tool(
    ticker: str,
    bullish: Dict[str, Any],
    bearish: Dict[str, Any],
    risk_tolerance: Literal["low","medium","high"] = "medium",
    time_horizon: Literal["short","medium","long"] = "medium"
) -> Dict[str, Any]:
    """
    Synthesize bullish and bearish research packs into a final decision.
    Inputs are the JSON outputs from researchers/bullish.py and researchers/bearish.py.
    Returns a decision pack JSON with BUY/SELL/HOLD + confidence, plus consensus,
    disagreements, risks/upside, rationale, and deduped evidence citations.
    """
    return await DebateModerator().run(
        ticker=ticker,
        bullish=bullish,
        bearish=bearish,
        risk_tolerance=risk_tolerance,
        time_horizon=time_horizon
    )
