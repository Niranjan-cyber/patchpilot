"""Registers AI steps into the worker graph (imported by backend/worker/main.py)."""
from backend.agents.reproduce import reproduce
from backend.contracts.models import StepId
from backend.worker import nodes

nodes.register(StepId.REPRODUCE, reproduce)
