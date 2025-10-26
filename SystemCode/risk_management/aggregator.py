"""Aggregate multiple risk perspectives into a single execution plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean
from typing import Iterable, List, Optional, Sequence, Tuple

from .schema import (
    AdjustmentBand,
    ConsistencyCheck,
    FinalExecutionPlan,
    RiskBudget,
    RiskManagementReport,
    RiskPerspective,
    RiskSynthesis,
    TraderDecisionCard,
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _baseline_position(card: TraderDecisionCard) -> float:
    if card.position_size and card.position_size.percentage is not None:
        return float(card.position_size.percentage)
    defaults = {"BUY": 0.1, "SELL": 0.12, "HOLD": 0.05}
    return defaults.get(card.decision, 0.08)


def _fallback_bands(card: TraderDecisionCard) -> Tuple[Optional[float], Optional[float]]:
    px = card.current_price
    if card.decision == "BUY":
        return round(px * 0.95, 4), round(px * 1.12, 4)
    if card.decision == "SELL":
        return round(px * 1.05, 4), round(px * 0.88, 4)
    return round(px * 0.97, 4), round(px * 1.03, 4)


def _aggregate_position(perspectives: Sequence[RiskPerspective], fallback: float) -> float:
    values = []
    for perspective in perspectives:
        adj = perspective.adjustments
        if adj and adj.position_size is not None:
            values.append(float(adj.position_size))
    if not values:
        return _clamp(fallback, 0.0, 0.5)
    return _clamp(mean(values), 0.0, 0.5)


def _aggregate_band_values(
    card: TraderDecisionCard,
    perspectives: Sequence[RiskPerspective],
) -> Tuple[Optional[float], Optional[float]]:
    stops = []
    takes = []
    for perspective in perspectives:
        adj = perspective.adjustments
        if adj:
            if adj.stop_loss is not None:
                stops.append(float(adj.stop_loss))
            if adj.take_profit is not None:
                takes.append(float(adj.take_profit))

    fallback_stop, fallback_take = _fallback_bands(card)

    if card.decision == "BUY":
        stop_loss = max(stops) if stops else fallback_stop
        take_profit = max(takes) if takes else fallback_take
    elif card.decision == "SELL":
        stop_loss = min(stops) if stops else fallback_stop
        take_profit = min(takes) if takes else fallback_take
    else:
        stop_loss = mean(stops) if stops else fallback_stop
        take_profit = mean(takes) if takes else fallback_take

    stop_loss = round(stop_loss, 4) if stop_loss is not None else None
    take_profit = round(take_profit, 4) if take_profit is not None else None
    return stop_loss, take_profit


def _aggregate_confidence(perspectives: Sequence[RiskPerspective]) -> float:
    confidences = [p.confidence for p in perspectives if p.confidence is not None]
    if not confidences:
        return 0.4
    return _clamp(mean(confidences), 0.05, 0.95)


def _aggregate_hedging(perspectives: Sequence[RiskPerspective]) -> List[str]:
    seen = set()
    ideas: List[str] = []
    for perspective in perspectives:
        for idea in perspective.adjustments.hedging_ideas if perspective.adjustments else []:
            key = idea.strip()
            if key and key not in seen:
                seen.add(key)
                ideas.append(key)
    return ideas[:6]


def _aggregate_notes(perspectives: Sequence[RiskPerspective]) -> List[str]:
    seen = set()
    notes: List[str] = []
    for perspective in perspectives:
        for note in perspective.adjustments.notes if perspective.adjustments else []:
            key = note.strip()
            if key and key not in seen:
                seen.add(key)
                notes.append(key)
    return notes[:6]


def _aggregate_rationale(perspectives: Sequence[RiskPerspective], max_items: int = 5) -> List[str]:
    rationale: List[str] = []
    for perspective in perspectives:
        summary = perspective.risk_summary.strip()
        if summary:
            rationale.append(summary)
    return rationale[:max_items]


def _aggregate_follow_up(perspectives: Sequence[RiskPerspective], max_items: int = 6) -> List[str]:
    follow_up: List[str] = []
    seen = set()
    for perspective in perspectives:
        for alert in perspective.alerts:
            key = alert.strip()
            if key and key not in seen:
                seen.add(key)
                follow_up.append(key)
    return follow_up[:max_items]


def _derive_action(decision: str, baseline: float, target: float) -> str:
    delta = target - baseline
    if decision == "BUY":
        if delta > 0.04:
            return "Scale into the long exposure with staged entries."
        if delta < -0.03:
            return "Trim the long exposure to protect capital."
        return "Maintain the long bias with refreshed risk bands."
    if decision == "SELL":
        if delta > 0.04:
            return "Increase short exposure carefully with firm stops."
        if delta < -0.03:
            return "Reduce the short exposure to limit drawdown risk."
        return "Maintain the short bias while monitoring catalysts."
    if target > baseline + 0.02:
        return "Take a measured position while keeping cash reserves."
    if target < baseline - 0.02:
        return "Reduce exposure and wait for clearer signals."
    return "Stay largely neutral and reassess after new data."


def _derive_risk_budget(target_position: float, confidence: float, decision: str) -> RiskBudget:
    exposure = abs(target_position)
    if decision == "HOLD" and exposure <= 0.06:
        return "low"
    if exposure >= 0.18 or confidence >= 0.75:
        return "high"
    if exposure >= 0.1:
        return "medium"
    return "low"


def _build_consistency_checks(
    card: TraderDecisionCard,
    target_position: float,
    stop_loss: Optional[float],
    take_profit: Optional[float],
    risk_budget: RiskBudget,
) -> List[ConsistencyCheck]:
    checks: List[ConsistencyCheck] = []

    baseline = _baseline_position(card)
    delta = target_position - baseline

    if card.decision == "HOLD":
        passed = target_position <= 0.12
        details = f"target size {target_position:.3f} while HOLD baseline {baseline:.3f}"
        checks.append(
            ConsistencyCheck(
                check="Position stays light under HOLD directive",
                passed=passed,
                severity="warning" if not passed else "info",
                details=details,
            )
        )
    else:
        passed = delta >= -0.06
        details = f"target size {target_position:.3f} vs baseline {baseline:.3f}"
        checks.append(
            ConsistencyCheck(
                check="Position aligns with trader direction",
                passed=passed,
                severity="warning" if not passed else "info",
                details=details,
            )
        )

    if stop_loss is None:
        checks.append(
            ConsistencyCheck(
                check="Stop-loss present",
                passed=False,
                severity="critical",
                details="No aggregated stop-loss; default bands recommended.",
            )
        )
    else:
        checks.append(
            ConsistencyCheck(
                check="Stop-loss present",
                passed=True,
                severity="info",
                details=f"Stop-loss at {stop_loss}",
            )
        )

    if take_profit is None:
        checks.append(
            ConsistencyCheck(
                check="Take-profit defined",
                passed=False,
                severity="warning",
                details="Add exit target to crystallise gains.",
            )
        )
    else:
        checks.append(
            ConsistencyCheck(
                check="Take-profit defined",
                passed=True,
                severity="info",
                details=f"Take-profit at {take_profit}",
            )
        )

    budget_notes = {
        "low": "Low risk budget consistent with light sizing.",
        "medium": "Moderate risk budget with balanced exposure.",
        "high": "High risk budget requires strict monitoring.",
    }
    checks.append(
        ConsistencyCheck(
            check="Risk budget rationale",
            passed=True,
            severity="info",
            details=budget_notes[risk_budget],
        )
    )

    return checks


@dataclass
class RiskAggregator:
    """Combine three modelled perspectives into a final risk synthesis."""

    include_raw: bool = field(default=False)

    def build_report(
        self,
        ticker: str,
        trader_card: TraderDecisionCard,
        perspectives: Sequence[RiskPerspective],
        meta: Optional[dict] = None,
    ) -> RiskManagementReport:
        if len(perspectives) < 3:
            raise ValueError("At least three perspectives are required.")

        baseline = _baseline_position(trader_card)
        target_position = _aggregate_position(perspectives, baseline)
        stop_loss, take_profit = _aggregate_band_values(trader_card, perspectives)
        confidence = _aggregate_confidence(perspectives)
        risk_budget = _derive_risk_budget(target_position, confidence, trader_card.decision)

        execution = FinalExecutionPlan(
            action=_derive_action(trader_card.decision, baseline, target_position),
            position_size=round(target_position, 3),
            stop_loss=stop_loss,
            take_profit=take_profit,
            hedging_ideas=_aggregate_hedging(perspectives),
            notes=_aggregate_notes(perspectives),
        )

        summary = (
            f"Risk desk synthesis for {ticker} aligns with trader direction ({trader_card.decision}) "
            "while unifying optimistic, neutral, and pessimistic safeguards."
        )

        synthesis = RiskSynthesis(
            summary=summary,
            confidence=confidence,
            risk_budget=risk_budget,
            execution=execution,
            rationale=_aggregate_rationale(perspectives),
            follow_up=_aggregate_follow_up(perspectives),
        )

        checks = _build_consistency_checks(trader_card, target_position, stop_loss, take_profit, risk_budget)

        meta_info = {
            "aggregated_at": datetime.utcnow().isoformat(),
            "baseline_position": round(baseline, 3),
            "include_raw": self.include_raw,
        }
        if meta:
            meta_info.update(meta)

        report = RiskManagementReport(
            ticker=ticker,
            as_of=datetime.utcnow().isoformat(),
            trader_decision=trader_card,
            perspectives=list(perspectives),
            synthesis=synthesis,
            consistency_checks=checks,
            meta=meta_info,
        )

        if not self.include_raw:
            report.trader_decision.raw = {}  # strip heavy payload if requested

        return report
