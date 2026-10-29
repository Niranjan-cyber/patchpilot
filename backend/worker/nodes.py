"""Step registry. Role B/A implement `run(ctx) -> GateResult | None` in backend/agents or backend/sandbox and
register here; the graph wiring in graph.py never changes for that."""
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from backend.contracts.models import CheckStatus, GateResult, RunView, StepId


@dataclass
class StepContext:
    run_id: str
    run: RunView
    emit: Callable[..., object]                                   # emit(type, step=None, **payload)
    scratch: dict = field(default_factory=dict)                   # per-run values steps hand each other


GATE_OF = {StepId.PREFLIGHT: "G1", StepId.SETUP: "G2", StepId.REPRODUCE: "G3", StepId.FIX: "G4",
           StepId.VERIFY: "G5", StepId.REVIEW: "G6"}
ORDER = [StepId.PREFLIGHT, StepId.SETUP, StepId.BASELINE, StepId.REPRODUCE, StepId.DIAGNOSE,
         StepId.FIX, StepId.VERIFY, StepId.REVIEW]


def _stub(step: StepId) -> Callable[[StepContext], GateResult | None]:
    def run(ctx: StepContext):
        time.sleep(float(os.getenv("STUB_STEP_SECONDS", "1")))
        # shortcut: unbuilt steps report not_run (never a fake pass); replaced as B05-B09 register real ones.
        ctx.scratch.setdefault("stub_steps", []).append(step.value)
        g = GATE_OF.get(step)
        return GateResult(gate=g, status=CheckStatus.NOT_RUN, reason="not_built_yet") if g else None
    return run


NODES: dict[StepId, Callable[[StepContext], GateResult | None]] = {s: _stub(s) for s in ORDER}


def register(step: StepId, fn: Callable[[StepContext], GateResult | None]) -> None:
    NODES[step] = fn
