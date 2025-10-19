"""Typed schemas shared by risk-management modules."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, validator


PerspectiveName = Literal["optimistic", "neutral", "pessimistic"]
ScenarioName = Literal["bull", "base", "bear"]
RiskBudget = Literal["low", "medium", "high"]


class TraderPositionSizing(BaseModel):
    percentage: float = Field(..., ge=0.0, le=1.0)
    description: Optional[str] = None


class TraderExecutionWindow(BaseModel):
    min_price: Optional[float] = Field(None, ge=0.0)
    max_price: Optional[float] = Field(None, ge=0.0)
    description: Optional[str] = None


class TraderRiskBand(BaseModel):
    price: Optional[float] = Field(None, ge=0.0)
    description: Optional[str] = None


class TraderDecisionCard(BaseModel):
    """Normalized view of the trader agent output for a single symbol."""

    symbol: str
    decision: Literal["BUY", "SELL", "HOLD"]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    current_price: float = Field(..., ge=0.0)
    reasoning: Optional[str] = None
    has_prediction: Optional[bool] = None
    timestamp: Optional[str] = None
    prediction_insight: Optional[str] = None
    position_size: Optional[TraderPositionSizing] = None
    execution_range: Optional[TraderExecutionWindow] = None
    stop_loss: Optional[TraderRiskBand] = None
    take_profit: Optional[TraderRiskBand] = None
    raw: Dict[str, Any] = Field(default_factory=dict)

    @validator("decision", pre=True)
    def _upper_decision(cls, value: Any) -> str:
        return str(value).upper()

    class Config:
        extra = "allow"


class AdjustmentBand(BaseModel):
    """Position and limit adjustments produced by each perspective."""

    position_size: Optional[float] = Field(None, ge=0.0, le=1.0)
    stop_loss: Optional[float] = Field(None, ge=0.0)
    take_profit: Optional[float] = Field(None, ge=0.0)
    hedging_ideas: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PerspectiveScenario(BaseModel):
    """Scenario planning row (bull/base/bear)."""

    name: ScenarioName
    trigger: str
    response_plan: str
    probability: Optional[float] = Field(None, ge=0.0, le=1.0)


class RiskPerspective(BaseModel):
    """Output from a single risk perspective (optimistic/neutral/pessimistic)."""

    view_name: PerspectiveName
    risk_summary: str
    adjustments: AdjustmentBand
    scenarios: List[PerspectiveScenario] = Field(..., min_items=1)
    alerts: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @validator("scenarios")
    def _enforce_three_scenarios(cls, value: List[PerspectiveScenario]) -> List[PerspectiveScenario]:
        if len(value) < 3:
            raise ValueError("scenarios must contain bull/base/bear entries")
        return value


class FinalExecutionPlan(BaseModel):
    """Actionable execution details after synthesising all perspectives."""

    action: str = Field(..., description="High level action label, e.g. 'Tighten long exposure'.")
    position_size: Optional[float] = Field(None, ge=0.0, le=1.0)
    stop_loss: Optional[float] = Field(None, ge=0.0)
    take_profit: Optional[float] = Field(None, ge=0.0)
    hedging_ideas: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RiskSynthesis(BaseModel):
    """Final synthesis across perspectives."""

    summary: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_budget: RiskBudget
    execution: FinalExecutionPlan
    rationale: List[str] = Field(default_factory=list)
    follow_up: List[str] = Field(default_factory=list)


class ConsistencyCheck(BaseModel):
    """Consistency diagnostics between trader decision and risk synthesis."""

    check: str
    passed: bool
    severity: Literal["info", "warning", "critical"] = "info"
    details: Optional[str] = None


class RiskManagementReport(BaseModel):
    """Top-level JSON payload returned to the manager agent."""

    ticker: str
    as_of: str
    trader_decision: TraderDecisionCard
    perspectives: List[RiskPerspective] = Field(..., min_items=3)
    synthesis: RiskSynthesis
    consistency_checks: List[ConsistencyCheck] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
