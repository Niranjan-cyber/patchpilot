"""Dump contract JSON Schema for web type generation (contracts: TS types are generated, never hand-written)."""
import json
from pydantic.json_schema import models_json_schema
from backend.contracts.models import ApiError, ApproveRequest, Event, RunView
from backend.github.reader import IssueCheck

_, schema = models_json_schema([(m, "serialization") for m in (RunView, Event, ApproveRequest, ApiError, IssueCheck)])
schema["title"] = "Contracts"
schema["properties"] = {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in (RunView, Event, ApproveRequest, ApiError, IssueCheck)}
open("web/src/contracts.schema.json", "w").write(json.dumps(schema, indent=1))
