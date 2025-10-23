"""Top-level orchestrator for the MarketLens risk-management pipeline."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .aggregator import RiskAggregator
from .neutral import NeutralRiskEvaluator
from .optimist import OptimisticRiskEvaluator
from .pessimist import PessimisticRiskEvaluator
from .schema import RiskManagementReport, RiskPerspective, TraderDecisionCard
from .utils import TraderDataError, ensure_output_directory, load_trader_decision
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskOrchestratorResult:
    """Return object for orchestration output."""

    report: RiskManagementReport
    saved_path: Path
    perspectives: Sequence[RiskPerspective]
    metadata: Dict[str, str]
    json_text: str


@dataclass
class RiskManagementOrchestrator:
    """Coordinate evaluators and produce the final risk report."""

    use_llm: bool = True
    max_workers: int = 3
    aggregator: RiskAggregator = field(default_factory=RiskAggregator)

    def _build_evaluators(self) -> List:
        return [
            OptimisticRiskEvaluator(use_llm=self.use_llm),
            NeutralRiskEvaluator(use_llm=self.use_llm),
            PessimisticRiskEvaluator(use_llm=self.use_llm),
        ]

    def _run_evaluators(self, card: TraderDecisionCard) -> List[RiskPerspective]:
        evaluators = self._build_evaluators()
        perspectives: List[RiskPerspective] = []

        if self.max_workers <= 1:
            for evaluator in evaluators:
                perspectives.append(evaluator.generate(card))
            return perspectives

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(evaluators))) as executor:
            future_map = {executor.submit(e.generate, card): e for e in evaluators}
            for future in as_completed(future_map):
                perspective = future.result()
                perspectives.append(perspective)

        # Preserve deterministic order: optimistic, neutral, pessimistic
        perspectives.sort(key=lambda p: {"optimistic": 0, "neutral": 1, "pessimistic": 2}[p.view_name])
        return perspectives

    def generate_report(
        self,
        ticker: str,
        trader_data: str,
        output_root: str = "database",
        include_raw: bool = False,
    ) -> RiskOrchestratorResult:
        """Run the full risk-management pipeline synchronously."""
        card, trader_meta = load_trader_decision(trader_data, ticker)
        self.aggregator.include_raw = include_raw

        perspectives = self._run_evaluators(card)

        meta = {
            "trader_source": trader_meta.get("source"),
            "available_symbols": trader_meta.get("available_symbols"),
        }
        report = self.aggregator.build_report(
            ticker=ticker,
            trader_card=card,
            perspectives=perspectives,
            meta=meta,
        )

        output_dir = ensure_output_directory(ticker, root=output_root)
        output_path = output_dir / f"risk_{ticker.upper()}.json"
        report_payload = report.model_dump()
        report_json = json.dumps(report_payload, ensure_ascii=False, indent=2)
        output_path.write_text(report_json, encoding="utf-8")

        return RiskOrchestratorResult(
            report=report,
            saved_path=output_path,
            perspectives=perspectives,
            metadata={"output_dir": str(output_dir), "trader_source": meta["trader_source"]},
            json_text=report_json,
        )


def run_risk_management(
    ticker: str,
    trader_data: str,
    output_root: str = "database",
    use_llm: bool = True,
    include_raw: bool = False,
) -> Tuple[str, Dict[str, str]]:
    """Convenience wrapper returning saved path and quick summary."""
    orchestrator = RiskManagementOrchestrator(use_llm=use_llm)
    logger.info(f"[RISK] 🛡️  Running risk management: {ticker.upper()}")
    result = orchestrator.generate_report(
        ticker=ticker,
        trader_data=trader_data,
        output_root=output_root,
        include_raw=include_raw,
    )
    logger.info(f"[RISK] 📄 Risk report saved: {result.saved_path}")
    logger.debug(f"[RISK] 📊 Risk report content:\n{result.json_text}")

    summary = {
        "ticker": ticker.upper(),
        "saved_path": str(result.saved_path),
        "risk_budget": result.report.synthesis.risk_budget,
        "confidence": f"{result.report.synthesis.confidence:.2f}",
        "position_size": f"{result.report.synthesis.execution.position_size or 0:.3f}",
    }
    return str(result.saved_path), summary
