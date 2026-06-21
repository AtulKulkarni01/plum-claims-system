"""Trace accumulator — the backbone of observability.

Every agent appends steps here. The orchestrator owns one instance per claim and
attaches the finished list to the result, so any decision can be reconstructed
end to end from the trace alone.
"""

from __future__ import annotations

from .models import StepStatus, TraceStep


class Trace:
    def __init__(self) -> None:
        self._steps: list[TraceStep] = []

    def add(
        self,
        step: str,
        status: StepStatus,
        detail: str,
        data: dict | None = None,
        confidence_delta: float = 0.0,
    ) -> TraceStep:
        entry = TraceStep(
            step=step,
            status=status,
            detail=detail,
            data=data or {},
            confidence_delta=confidence_delta,
        )
        self._steps.append(entry)
        return entry

    @property
    def steps(self) -> list[TraceStep]:
        return self._steps

    def total_confidence_delta(self) -> float:
        return sum(s.confidence_delta for s in self._steps)
