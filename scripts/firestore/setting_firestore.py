#!/usr/bin/env python3
"""
Utility script to align Firestore exposure config and per-strategy guardrails.

Example (defaults):
    python setting_firestore.py \
        --project-id gold-gearbox-424413-k1

Override weights / notional limits:
    python setting_firestore.py \
        --project-id gold-gearbox-424413-k1 \
        --overall-exposure 0.85 \
        --testsignalgenerator-weight 0.30 \
        --spy-macd-vixy-weight 0.30 \
        --reserve-weight 0.40 \
        --testsignalgenerator-max-notional 500000 \
        --spy-macd-vixy-max-notional 700000
"""

from __future__ import annotations

import argparse
import json
from typing import Dict, Any

from google.cloud import firestore  # type: ignore[import]


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(f"Not a valid float: {value}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("Value must be non-negative")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Firestore exposure config and strategy guardrails.")
    parser.add_argument("--project-id", required=True, help="GCP project id hosting Firestore.")

    # Exposure knobs
    parser.add_argument("--overall-exposure", type=_positive_float, default=0.90, help="Overall capital deployment ratio.")
    parser.add_argument("--testsignalgenerator-weight", type=_positive_float, default=0.20, help="test signal generator share (0-1).")
    parser.add_argument("--spy-macd-vixy-weight", type=_positive_float, default=0.20, help="spy_macd_vixy share (0-1).")
    parser.add_argument("--ib-macd-stoch-weight", type=_positive_float, default=0.20, help="ib_macd_stoch share (0-1).")
    parser.add_argument("--reserve-weight", type=_positive_float, default=0.20, help="Reserve bucket share (0-1).")

    # Per-strategy guardrails
    parser.add_argument("--testsignalgenerator-max-notional", type=_positive_float, default=600_000.0)
    parser.add_argument("--spy-macd-vixy-max-notional", type=_positive_float, default=600_000.0)
    parser.add_argument("--ib-macd-stoch-max-notional", type=_positive_float, default=600_000.0)
    parser.add_argument(
        "--ib-macd-stoch-allowed-symbols",
        nargs="+",
        default=["META", "AMZN", "TSLA", "MSFT", "AAPL"],
        help="Allowed symbols for ib_macd_stoch guardrail.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without writing to Firestore.")
    return parser.parse_args()


def _build_exposure_payload(args: argparse.Namespace) -> Dict[str, Any]:
    strategies = {
        "testsignalgenerator": round(args.testsignalgenerator_weight, 6),
        "spy_macd_vixy": round(args.spy_macd_vixy_weight, 6),
        "ib_macd_stoch": round(args.ib_macd_stoch_weight, 6),
        "reserve_pool": round(args.reserve_weight, 6),
    }
    return {"exposure": {"overall": round(args.overall_exposure, 6), "strategies": strategies}}


def _build_strategy_payloads(args: argparse.Namespace) -> Dict[str, Dict[str, Any]]:
    return {
        "testsignalgenerator": {
            "allowed_symbols": ["SPY"],
            "max_notional": args.testsignalgenerator_max_notional,
        },
        "spy_macd_vixy": {
            "allowed_symbols": ["SPY", "VIXY"],
            "max_notional": args.spy_macd_vixy_max_notional,
        },
        "ib_macd_stoch": {
            "allowed_symbols": args.ib_macd_stoch_allowed_symbols,
            "max_notional": args.ib_macd_stoch_max_notional,
        },
    }


def main() -> int:
    args = _parse_args()
    exposure_payload = _build_exposure_payload(args)
    strategy_payloads = _build_strategy_payloads(args)

    print("=== Planned Firestore updates ===")
    print("config/common:\n", json.dumps(exposure_payload, indent=2))
    print("strategies payloads:\n", json.dumps(strategy_payloads, indent=2))

    if args.dry_run:
        print("Dry-run enabled; no changes applied.")
        return 0

    client = firestore.Client(project=args.project_id)
    client.collection("config").document("common").set(exposure_payload, merge=True)
    for strategy_id, payload in strategy_payloads.items():
        client.collection("strategies").document(strategy_id).set(payload, merge=True)
    print("Firestore updates applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
