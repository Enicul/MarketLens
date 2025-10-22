"""Optimistic risk perspective evaluator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Tuple

from langchain.prompts import ChatPromptTemplate
from config import LLM_GOOGLE

from .schema import (
    AdjustmentBand,
    PerspectiveScenario,
    RiskPerspective,
    TraderDecisionCard,
)


PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are the optimistic risk officer for an investment desk. "
            "Given a trader decision card, produce a JSON object describing an optimistic "
            "but still risk-aware plan. The JSON must match the provided schema exactly.",
        ),
        (
            "human",
            "Ticker: {ticker}\n"
            "Perspective: optimistic\n"
            "Trader decision (JSON):\n{trader_json}\n\n"
            "Target JSON schema:\n{schema_json}\n"
            "Remember: return ONLY the JSON payload.",
        ),
    ]
)


def _safe_clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _default_position(trader: TraderDecisionCard) -> float:
    if trader.position_size and trader.position_size.percentage is not None:
        return float(trader.position_size.percentage)
    default_map = {"BUY": 0.12, "SELL": 0.12, "HOLD": 0.05}
    return default_map.get(trader.decision, 0.08)


def _default_bands(trader: TraderDecisionCard) -> Tuple[Optional[float], Optional[float]]:
    stop = trader.stop_loss.price if trader.stop_loss else None
    take = trader.take_profit.price if trader.take_profit else None

    px = trader.current_price
    if trader.decision == "BUY":
        stop = stop or px * 0.95
        take = take or px * 1.15
    elif trader.decision == "SELL":
        stop = stop or px * 1.05
        take = take or px * 0.85
    else:  # HOLD
        if stop is None:
            stop = px * 0.97
        if take is None:
            take = px * 1.03

    return round(stop, 4) if stop else None, round(take, 4) if take else None


def _build_scenarios(trader: TraderDecisionCard, target_position: float) -> list[PerspectiveScenario]:
    px = trader.current_price
    bull_trigger = f"Breakout above {px * 1.05:.2f} with volume expansion."
    base_trigger = f"Price consolidates around {px:.2f} with neutral flows."
    bear_trigger = f"Close below {px * 0.95:.2f} on risk-off sentiment."

    return [
        PerspectiveScenario(
            name="bull",
            trigger=bull_trigger,
            response_plan=f"Add exposure up to {target_position + 0.03:.2f} if breakout holds two sessions.",
            probability=0.45,
        ),
        PerspectiveScenario(
            name="base",
            trigger=base_trigger,
            response_plan="Maintain position, trail stop by 3% and reassess weekly.",
            probability=0.35,
        ),
        PerspectiveScenario(
            name="bear",
            trigger=bear_trigger,
            response_plan="Tighten stop-loss to entry price and consider protective calls.",
            probability=0.20,
        ),
    ]


@dataclass
class OptimisticRiskEvaluator:
    """Produce a RiskPerspective biased toward upside capture."""
    
    use_llm: bool = True

    def __post_init__(self) -> None:
        self._llm: Optional[LLM_GOOGLE] = None
        if self.use_llm:
            self._llm = LLM_GOOGLE
    @property
    def view_name(self) -> str:
        return "optimistic"

    def generate(self, trader_card: TraderDecisionCard) -> RiskPerspective:
        perspective = self._llm_generate(trader_card)
        if perspective:
            return perspective
        return self._rule_based(trader_card)

    def _llm_generate(self, trader_card: TraderDecisionCard) -> Optional[RiskPerspective]:
        if not self._llm:
            return None
            
        try:
            schema_json = RiskPerspective.schema_json(indent=2, sort_keys=True)
            trader_json = json.dumps(
                trader_card.dict(exclude={"raw"}), ensure_ascii=False, indent=2, sort_keys=True
            )
            messages = PROMPT.format_messages(
                ticker=trader_card.symbol,
                trader_json=trader_json,
                schema_json=schema_json,
            )
            raw = self._llm.invoke(messages).content
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None  # Fall back to rule-based instead of raising error
            payload = json.loads(raw[start : end + 1])
            perspective = RiskPerspective.parse_obj(payload)
            return perspective
        except Exception:
            return None  # Fall back to rule-based on any error

    def _rule_based(self, trader_card: TraderDecisionCard) -> RiskPerspective:
        base_position = _default_position(trader_card)
        if trader_card.decision == "BUY":
            target_position = _safe_clamp(base_position * 1.3, 0.0, 0.4)
        elif trader_card.decision == "SELL":
            target_position = _safe_clamp(base_position * 1.1, 0.0, 0.3)
        else:
            target_position = _safe_clamp(base_position * 1.05, 0.0, 0.2)

        stop_loss, take_profit = _default_bands(trader_card)
        if trader_card.decision == "BUY" and take_profit is not None:
            take_profit = round(take_profit * 1.05, 4)
        elif trader_card.decision == "SELL" and take_profit is not None:
            take_profit = round(take_profit * 0.97, 4)

        confidence = _safe_clamp(trader_card.confidence_score + 0.2, 0.1, 0.9)
        adjustments = AdjustmentBand(
            position_size=round(target_position, 3),
            stop_loss=stop_loss,
            take_profit=take_profit,
            hedging_ideas=[
                "Scale into the position with staggered entries to manage slippage.",
                "Use trailing stops to lock in gains if momentum accelerates.",
            ],
            notes=[
                "Optimistic bias assumes catalysts materialize within the next quarter.",
                "Review conviction if implied volatility spikes above 80th percentile.",
            ],
        )

        scenarios = _build_scenarios(trader_card, target_position)
        alerts = [
            "Track top-line catalysts (earnings, product launches, macro data) weekly.",
            "Watch credit spreads; widening above recent averages weakens the upside case.",
        ]
        summary = (
            f"Optimistic view seeks to capture additional upside in {trader_card.symbol} while "
            "maintaining disciplined exit bands."
        )

        return RiskPerspective(
            view_name="optimistic",
            risk_summary=summary,
            adjustments=adjustments,
            scenarios=scenarios,
            alerts=alerts,
            confidence=confidence,
        )
