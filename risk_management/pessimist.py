"""Pessimistic risk perspective evaluator."""

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
            "You are the pessimistic risk officer for an investment desk. "
            "Stress downside scenarios and produce JSON aligned with the schema.",
        ),
        (
            "human",
            "Ticker: {ticker}\n"
            "Perspective: pessimistic\n"
            "Trader decision (JSON):\n{trader_json}\n\n"
            "Target JSON schema:\n{schema_json}\n"
            "Respond with the JSON object only.",
        ),
    ]
)


def _safe_clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _default_position(trader: TraderDecisionCard) -> float:
    if trader.position_size and trader.position_size.percentage is not None:
        return float(trader.position_size.percentage)
    default_map = {"BUY": 0.08, "SELL": 0.12, "HOLD": 0.03}
    return default_map.get(trader.decision, 0.06)


def _default_bands(trader: TraderDecisionCard) -> Tuple[Optional[float], Optional[float]]:
    stop = trader.stop_loss.price if trader.stop_loss else None
    take = trader.take_profit.price if trader.take_profit else None

    px = trader.current_price
    if trader.decision == "BUY":
        stop = stop or px * 0.92
        take = take or px * 1.08
    elif trader.decision == "SELL":
        stop = stop or px * 1.03
        take = take or px * 0.82
    else:
        stop = stop or px * 0.96
        take = take or px * 1.02

    return round(stop, 4) if stop else None, round(take, 4) if take else None


def _build_scenarios(trader: TraderDecisionCard, target_position: float) -> list[PerspectiveScenario]:
    px = trader.current_price
    bull_trigger = f"Unexpected relief rally above {px * 1.03:.2f} on strong catalysts."
    base_trigger = f"Sideways chop around {px:.2f} amid mixed data."
    bear_trigger = f"Sharp drop below {px * 0.93:.2f} driven by risk-off flows."

    reduce_plan = "Cut risk by at least 50% and rotate into cash or defensive assets."
    return [
        PerspectiveScenario(
            name="bull",
            trigger=bull_trigger,
            response_plan="Keep exposure capped and trail stops tightly; avoid chasing strength.",
            probability=0.25,
        ),
        PerspectiveScenario(
            name="base",
            trigger=base_trigger,
            response_plan=f"Hold reduced sizing near {target_position:.2f} and maintain hedges.",
            probability=0.30,
        ),
        PerspectiveScenario(
            name="bear",
            trigger=bear_trigger,
            response_plan=reduce_plan,
            probability=0.45,
        ),
    ]


@dataclass
class PessimisticRiskEvaluator:
    """Produce a RiskPerspective focused on downside containment."""

    def __post_init__(self) -> None:
        self._llm = LLM_GOOGLE

    @property
    def view_name(self) -> str:
        return "pessimistic"

    def generate(self, trader_card: TraderDecisionCard) -> RiskPerspective:
        perspective = self._llm_generate(trader_card)
        if perspective:
            return perspective
        return self._rule_based(trader_card)

    def _llm_generate(self, trader_card: TraderDecisionCard) -> Optional[RiskPerspective]:
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
            raise ValueError("LLM response did not contain JSON.")
        payload = json.loads(raw[start : end + 1])
        perspective = RiskPerspective.parse_obj(payload)
        return perspective

    def _rule_based(self, trader_card: TraderDecisionCard) -> RiskPerspective:
        base_position = _default_position(trader_card)
        if trader_card.decision == "BUY":
            target_position = _safe_clamp(base_position * 0.6, 0.0, 0.18)
        elif trader_card.decision == "SELL":
            target_position = _safe_clamp(base_position * 1.2, 0.0, 0.35)
        else:
            target_position = _safe_clamp(base_position * 0.5, 0.0, 0.1)

        stop_loss, take_profit = _default_bands(trader_card)
        confidence = _safe_clamp(0.35 + (1.0 - trader_card.confidence_score) * 0.6, 0.25, 0.85)

        adjustments = AdjustmentBand(
            position_size=round(target_position, 3),
            stop_loss=stop_loss,
            take_profit=take_profit,
            hedging_ideas=[
                "Initiate protective puts or put spreads to guard tail events.",
                "Consider pairs trades to neutralize beta exposure.",
                "Shift part of exposure into cash or treasuries during stress.",
            ],
            notes=[
                "Pessimistic stance assumes volatility remains elevated.",
                "Rebuild exposure only after downside catalysts clear and breadth stabilizes.",
            ],
        )

        scenarios = _build_scenarios(trader_card, target_position)
        alerts = [
            "Monitor liquidity conditions; widening bid-ask spreads signal exit urgency.",
            "Track credit default swaps and funding markets for early stress indicators.",
        ]
        summary = (
            f"Pessimistic view for {trader_card.symbol} emphasises capital protection and rapid de-risking."
        )

        return RiskPerspective(
            view_name="pessimistic",
            risk_summary=summary,
            adjustments=adjustments,
            scenarios=scenarios,
            alerts=alerts,
            confidence=confidence,
        )
