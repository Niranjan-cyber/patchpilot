"""Registers AI steps into the worker graph (imported by backend/worker/main.py)."""
from backend.agents.diagnose import diagnose
from backend.agents.fix import fix
from backend.agents.reproduce import reproduce
from backend.contracts.models import StepId
from backend.worker import nodes

nodes.register(StepId.REPRODUCE, reproduce)
nodes.register(StepId.DIAGNOSE, diagnose)
nodes.register(StepId.FIX, fix)
from backend.agents.verify import verify  # noqa: E402
nodes.register(StepId.VERIFY, verify)
