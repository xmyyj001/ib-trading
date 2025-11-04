"""
Utilities for normalizing Interactive Brokers dataclasses so they can be
persisted in Firestore or logged safely.
"""

from dataclasses import fields, is_dataclass
from typing import Any, Dict

from ib_insync import Contract


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


def _object_to_mapping(obj: Any) -> Dict[str, Any]:
    """
    Convert an ``ib_insync`` object (contract/order/etc.) into a mutable mapping.
    """
    if is_dataclass(obj):
        # Extract dataclass fields explicitly to avoid util.dataclassAsDict.
        return {field.name: getattr(obj, field.name) for field in fields(obj)}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return {
            key: getattr(obj, key)
            for key in obj.__dict__
            if not key.startswith("_")
        }
    if hasattr(obj, "__slots__"):
        mapping: Dict[str, Any] = {}
        for slot in obj.__slots__:
            if slot.startswith("_"):
                continue
            try:
                mapping[slot] = getattr(obj, slot)
            except AttributeError:
                continue
        if mapping:
            return mapping
    return {"value": obj}


def _normalize_mapping(data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply pruning rules to an object's mapping representation."""
    normalized: Dict[str, Any] = {}
    for key, raw in data.items():
        value = _prune_empty(raw)
        if value not in (None, {}, [], ""):
            normalized[key] = value
    return normalized


def contract_to_dict(contract: Any) -> Dict[str, Any]:
    """
    Serialize an ``ib_insync`` contract (or nested dataclasses) into a dict.

    ``ib_insync.util.contractToDict`` was removed in recent releases, so we
    emulate the behaviour locally without depending on ``ib_insync`` internals.
    """
    if not contract:
        return {}

    data = _object_to_mapping(contract)
    return _normalize_mapping(data)


def dict_to_contract(data: Dict[str, Any]) -> Contract:
    """
    Reconstruct an ``ib_insync.Contract`` (or compatible subclass) from a dict
    previously produced by :func:`contract_to_dict`.
    """
    contract = Contract()
    if not data:
        return contract

    for key, value in data.items():
        try:
            setattr(contract, key, value)
        except (AttributeError, TypeError):
            # Ignore attributes that cannot be set on the base contract
            continue
    return contract


def order_to_dict(order: Any) -> Dict[str, Any]:
    """
    Serialize an ``ib_insync.Order`` (or compatible object) into a dict.

    ``ib_insync.util.orderToDict`` was removed in recent releases, so we follow
    the same pruning rules used for contracts.
    """
    if not order:
        return {}

    data = _object_to_mapping(order)
    return _normalize_mapping(data)
