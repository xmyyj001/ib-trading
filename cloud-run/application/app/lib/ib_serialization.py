"""
Utilities for normalizing Interactive Brokers dataclasses so they can be
persisted in Firestore or logged safely.
"""

from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from ib_insync import util


def _prune_empty(value: Any) -> Any:
    """Recursively prune empty / None values to keep documents compact."""
    if isinstance(value, list):
        items = [_prune_empty(item) for item in value]
        return [item for item in items if item not in (None, {}, [], "")]
    if isinstance(value, dict):
        pruned = {k: _prune_empty(v) for k, v in value.items()}
        return {k: v for k, v in pruned.items() if v not in (None, {}, [], "")}
    if is_dataclass(value):
        return contract_to_dict(value)
    return value


def contract_to_dict(contract: Any) -> Dict[str, Any]:
    """
    Serialize an ``ib_insync`` contract (or nested dataclasses) into a dict.

    ``ib_insync.util.contractToDict`` was removed in recent releases, so we
    emulate the old behaviour via ``dataclassAsDict`` while pruning empty fields.
    """
    if not contract:
        return {}

    if is_dataclass(contract):
        data = util.dataclassAsDict(contract)
    elif hasattr(contract, "__dict__"):
        data = {k: getattr(contract, k) for k in dir(contract) if not k.startswith("_")}
    else:
        # Fallback: try dataclasses.asdict for unknown containers.
        try:
            data = asdict(contract)  # type: ignore[arg-type]
        except TypeError:
            return {"value": contract}

    normalized: Dict[str, Any] = {}
    for key, raw in data.items():
        value = _prune_empty(raw)
        if value not in (None, {}, [], ""):
            normalized[key] = value
    return normalized
