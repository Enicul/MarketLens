"""Shared utilities for MarketLens risk management."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from pydantic import ValidationError

from .schema import TraderDecisionCard

JsonLike = Union[str, Dict[str, Any], List[Any]]


class TraderDataError(RuntimeError):
    """Raised when trader data cannot be parsed or does not match expectations."""


def _load_json_from_any(raw: JsonLike) -> Tuple[Any, str]:
    """Load JSON-like content from inline string, dict/list, or filesystem path."""
    if isinstance(raw, (dict, list)):
        return raw, "<inline>"

    if raw is None:
        raise TraderDataError("trader_data is empty")

    text = str(raw).strip()
    if not text:
        raise TraderDataError("trader_data is empty")

    if text[0] in "{[":
        try:
            return json.loads(text), "<inline>"
        except json.JSONDecodeError as exc:
            raise TraderDataError(f"unable to parse trader_data JSON: {exc}") from exc

    path = Path(text)
    if not path.exists():
        raise TraderDataError(f"trader_data file not found: {text}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data, str(path)
    except json.JSONDecodeError as exc:
        raise TraderDataError(f"file does not contain valid JSON: {path}") from exc


def _iter_candidate_cards(payload: Any) -> Iterable[Dict[str, Any]]:
    """Yield candidate card dictionaries from various trader response formats."""
    if isinstance(payload, dict):
        symbols = payload.get("symbols")
        if isinstance(symbols, list):
            for item in symbols:
                if isinstance(item, dict):
                    yield item
        else:
            yield payload
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item


def _select_card(payload: Any, ticker: Optional[str]) -> Dict[str, Any]:
    """Select the trader card matching the ticker (or the first available one)."""
    candidates = list(_iter_candidate_cards(payload))
    if not candidates:
        raise TraderDataError("no trader decision cards found in payload")

    if ticker:
        target = ticker.upper()
        for card in candidates:
            symbol = str(card.get("symbol", "")).upper()
            if symbol == target:
                return card

    return candidates[0]


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _normalize_card_fields(card: Dict[str, Any], ticker: Optional[str]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(card)

    if ticker:
        normalized.setdefault("symbol", ticker.upper())

    # Decision
    if "decision" in normalized:
        normalized["decision"] = str(normalized["decision"]).upper()
    elif "recommendation" in normalized:
        normalized["decision"] = str(normalized["recommendation"]).upper()

    # Confidence
    conf = normalized.get("confidence_score")
    if conf is None:
        conf = normalized.get("confidence")
    conf_val = _to_float(conf)
    if conf_val is not None:
        if conf_val > 1:
            conf_val = conf_val / 100.0
        conf_val = max(0.0, min(conf_val, 1.0))
        normalized["confidence_score"] = float(conf_val)
    else:
        normalized["confidence_score"] = 0.5

    # Current price
    price = _to_float(normalized.get("current_price"))
    normalized["current_price"] = price if price is not None else 0.0

    # Position size handling
    pos = normalized.get("position_size")
    pct_val: Optional[float] = None
    if isinstance(pos, dict):
        pct_val = _to_float(pos.get("percentage"))
        if pct_val is None:
            for key in ("value", "amount", "size"):
                pct_val = _to_float(pos.get(key))
                if pct_val is not None:
                    break
    else:
        pct_val = _to_float(pos)

    if pct_val is not None:
        while pct_val > 1:
            pct_val = pct_val / 100.0
        pct_val = max(0.0, min(pct_val, 1.0))
        normalized["position_size"] = {"percentage": pct_val}

    # Execution range
    exec_range = normalized.get("execution_range")
    if isinstance(exec_range, (list, tuple)) and len(exec_range) == 2:
        normalized["execution_range"] = {
            "min_price": _to_float(exec_range[0]),
            "max_price": _to_float(exec_range[1]),
            "description": "Derived execution window from trader output.",
        }
    elif isinstance(exec_range, dict):
        min_price = _to_float(exec_range.get("min_price", exec_range.get("min")))
        max_price = _to_float(exec_range.get("max_price", exec_range.get("max")))
        normalized["execution_range"] = {
            "min_price": min_price,
            "max_price": max_price,
            "description": exec_range.get("description", "Derived execution window from trader output."),
        }

    # Risk bands
    for key in ("stop_loss", "take_profit"):
        val = normalized.get(key)
        if isinstance(val, dict):
            price = _to_float(val.get("price"))
            normalized[key] = {
                "price": price,
                "description": val.get("description", f"Derived {key.replace('_', ' ')} from trader output."),
            }
        else:
            price = _to_float(val)
            if price is not None:
                normalized[key] = {
                    "price": price,
                    "description": f"Derived {key.replace('_', ' ')} from trader output.",
                }

    # Reasoning fallback
    if not normalized.get("reasoning"):
        for candidate in ("rationale", "summary", "analysis", "details"):
            text = normalized.get(candidate)
            if isinstance(text, str) and text.strip():
                normalized["reasoning"] = text.strip()
                break

    # has_prediction normalization
    if "has_prediction" in normalized:
        normalized["has_prediction"] = bool(normalized["has_prediction"])

    return normalized


def _parse_text_card(text: str, ticker: Optional[str]) -> Optional[Dict[str, Any]]:
    """Attempt to extract key fields from unstructured trader text output."""
    clean = text.replace("\\n", "\n")
    symbol = ticker.upper() if ticker else None

    decision_match = re.search(r"(BUY|SELL|HOLD)", clean, re.IGNORECASE)
    decision = decision_match.group(1).upper() if decision_match else "HOLD"

    conf_match = re.search(r"(?:confidence(?: score)?)[^0-9]*([\d\.]+)", clean, re.IGNORECASE)
    confidence = float(conf_match.group(1)) if conf_match else 50.0

    bullet_lines = [
        line.strip()
        for line in clean.splitlines()
        if line.strip().startswith("-") and any(ch.isdigit() for ch in line)
    ]

    def first_number(line: str) -> Optional[float]:
        match = re.search(r"\d+(?:\.\d+)?", line)
        return float(match.group(0)) if match else None

    def two_numbers(line: str) -> Tuple[Optional[float], Optional[float]]:
        matches = re.findall(r"\d+(?:\.\d+)?", line)
        if len(matches) >= 2:
            return float(matches[0]), float(matches[1])
        if matches:
            value = float(matches[0])
            return value, None
        return None, None

    current_price = first_number(bullet_lines[0]) if len(bullet_lines) >= 1 else None
    position_pct = first_number(bullet_lines[1]) if len(bullet_lines) >= 2 else None
    min_price, max_price = two_numbers(bullet_lines[2]) if len(bullet_lines) >= 3 else (None, None)
    stop_price = first_number(bullet_lines[3]) if len(bullet_lines) >= 4 else None
    take_price = first_number(bullet_lines[4]) if len(bullet_lines) >= 5 else None

    if current_price is None:
        price_match = re.search(r"(?:current price|last price|spot price)[^\d]*(\d+(?:\.\d+)?)", clean, re.IGNORECASE)
        current_price = float(price_match.group(1)) if price_match else 0.0
    if position_pct is None:
        pos_match = re.search(r"(?:recommended position|position|allocation)(?:[^0-9]+)(\d+(?:\.\d+)?)", clean, re.IGNORECASE)
        position_pct = float(pos_match.group(1)) if pos_match else 5.0
    if min_price is None or max_price is None:
        min_price = max(0.0, (current_price or 0.0) * 0.98) if min_price is None else min_price
        max_price = (current_price or 0.0) * 1.02 if max_price is None else max_price

    pct = position_pct or 0.0
    while pct > 1:
        pct /= 100.0
    pct = max(0.0, min(pct, 1.0))

    reasoning = clean.strip().split("\n\n")[-1].strip() if clean.strip() else ""

    card = {
        "symbol": symbol or "UNKNOWN",
        "decision": decision,
        "confidence_score": max(0.0, min(confidence / 100 if confidence > 1 else confidence, 1.0)),
        "current_price": current_price,
        "position_size": {"percentage": pct},
        "execution_range": {
            "min_price": min_price,
            "max_price": max_price,
            "description": "Parsed from textual trader output.",
        },
        "stop_loss": {
            "price": stop_price,
            "description": "Parsed stop loss from textual trader output.",
        } if stop_price is not None else None,
        "take_profit": {
            "price": take_price,
            "description": "Parsed take profit from textual trader output.",
        } if take_price is not None else None,
        "reasoning": reasoning,
    }
    return card


def load_trader_decision(trader_data: JsonLike, ticker: Optional[str] = None) -> Tuple[TraderDecisionCard, Dict[str, Any]]:
    """Parse trader output into a TraderDecisionCard plus metadata."""
    payload, source = _load_json_from_any(trader_data)

    if isinstance(payload, str):
        text_card = _parse_text_card(payload, ticker)
        if not text_card:
            raise TraderDataError("unable to parse trader text output into structured data")
        raw_copy = {"raw_text": payload}
        card = TraderDecisionCard.parse_obj({**text_card, "raw": raw_copy})
        metadata = {
            "source": source,
            "matched_symbol": card.symbol,
            "available_symbols": [card.symbol],
        }
        return card, metadata

    card_dict = _select_card(payload, ticker)

    # Preserve the raw payload for downstream traceability
    raw_copy = json.loads(json.dumps(card_dict))

    try:
        card = TraderDecisionCard.parse_obj({**card_dict, "raw": raw_copy})
    except ValidationError as exc:
        normalized_dict = _normalize_card_fields(card_dict, ticker)
        try:
            card = TraderDecisionCard.parse_obj({**normalized_dict, "raw": raw_copy})
        except ValidationError as exc2:
            raise TraderDataError(f"trader decision card failed validation: {exc2}") from exc2

    metadata = {
        "source": source,
        "matched_symbol": card.symbol,
        "available_symbols": [
            str(item.get("symbol", "")).upper()
            for item in _iter_candidate_cards(payload)
        ],
    }

    return card, metadata


def ensure_output_directory(ticker: str, root: Union[str, Path] = "database") -> Path:
    """Ensure the standard database directory exists for the given ticker."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    target = Path(root) / today / ticker.upper()
    target.mkdir(parents=True, exist_ok=True)
    return target
