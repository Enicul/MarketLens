"""Neutral risk perspective evaluator."""

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
            "You are the neutral risk officer for an investment desk. "
            "Blend upside and downside considerations and produce JSON that matches the supplied schema.",
        ),
        (
            "human",
            "Ticker: {ticker}\n"
            "Perspective: neutral\n"
            "Trader decision (JSON):\n{trader_json}\n\n"
            "Target JSON schema:\n{schema_json}\n"
            "Respond ONLY with the JSON payload.",
        ),
    ]
)


def _safe_clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _default_position(trader: TraderDecisionCard) -> float:
    if trader.position_size and trader.position_size.percentage is not None:
        return float(trader.position_size.percentage)
    default_map = {"BUY": 0.1, "SELL": 0.1, "HOLD": 0.05}
    return default_map.get(trader.decision, 0.08)


def _default_bands(trader: TraderDecisionCard) -> Tuple[Optional[float], Optional[float]]:
    stop = trader.stop_loss.price if trader.stop_loss else None
    take = trader.take_profit.price if trader.take_profit else None

    px = trader.current_price
    if trader.decision == "BUY":
        stop = stop or px * 0.94
        take = take or px * 1.12
    elif trader.decision == "SELL":
        stop = stop or px * 1.06
        take = take or px * 0.88
    else:
        stop = stop or px * 0.97
        take = take or px * 1.03

    return round(stop, 4) if stop else None, round(take, 4) if take else None


def _build_scenarios(trader: TraderDecisionCard, target_position: float) -> list[PerspectiveScenario]:
    px = trader.current_price
    bull_trigger = f"Close above {px * 1.04:.2f} with improving breadth."
    base_trigger = f"Range-bound action near {px:.2f} with balanced flows."
    bear_trigger = f"Break below {px * 0.96:.2f} on rising volatility."

    return [
        PerspectiveScenario(
            name="bull",
            trigger=bull_trigger,
            response_plan=f"Allow exposure to drift up to {target_position + 0.02:.2f} while monitoring volume.",
            probability=0.33,
        ),
        PerspectiveScenario(
            name="base",
            trigger=base_trigger,
            response_plan="Hold current sizing and refresh hedges monthly.",
            probability=0.34,
        ),
        PerspectiveScenario(
            name="bear",
            trigger=bear_trigger,
            response_plan="Trim exposure by 25% and add light downside hedges.",
            probability=0.33,
        ),
    ]


@dataclass
class NeutralRiskEvaluator:
    """Produce a RiskPerspective with balanced risk posture."""

    def __post_init__(self) -> None:
        self._llm = LLM_GOOGLE
    @property
    def view_name(self) -> str:
        return "neutral"

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
        if trader_card.decision == "HOLD":
            target_position = _safe_clamp(base_position * 0.8, 0.0, 0.15)
        else:
            target_position = _safe_clamp(base_position, 0.0, 0.25)

        stop_loss, take_profit = _default_bands(trader_card)
        confidence = _safe_clamp(0.4 + trader_card.confidence_score * 0.6, 0.2, 0.85)

        adjustments = AdjustmentBand(
            position_size=round(target_position, 3),
            stop_loss=stop_loss,
            take_profit=take_profit,
            hedging_ideas=[
                "Maintain a small options collar to smooth tail risk.",
                "Balance sector exposure with correlated longs/shorts.",
            ],
            notes=[
                "Neutral posture prioritizes capital preservation while keeping optionality.",
                "Revisit conviction if macro indicators move two standard deviations.",
            ],
        )

        scenarios = _build_scenarios(trader_card, target_position)
        alerts = [
            "Review macro calendar for asymmetric event risk each week.",
            "Track realized vs implied volatility; adjust hedges if spread widens.",
        ]
        summary = (
            f"Neutral view on {trader_card.symbol} maintains current risk with symmetrical guardrails."
        )

        return RiskPerspective(
            view_name="neutral",
            risk_summary=summary,
            adjustments=adjustments,
            scenarios=scenarios,
            alerts=alerts,
            confidence=confidence,
        )
