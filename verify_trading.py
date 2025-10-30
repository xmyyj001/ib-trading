#!/usr/bin/env python3
"""
Quick Firestore sanity check for Commander exposure math.

Example:
    python verify_trading.py --project-id gold-gearbox-424413-k1 --strategies spy_macd_vixy testsignalgenerator
"""

import argparse
import json
import sys
from typing import Dict, List, Optional

from google.cloud import firestore  # type: ignore[import]


def load_common_config(client: firestore.Client) -> Dict:
    doc = client.collection("config").document("common").get()
    if not doc.exists:
        raise RuntimeError("config/common document not found.")
    return doc.to_dict() or {}


def load_portfolio_snapshot(client: firestore.Client, trading_mode: str) -> Dict:
    doc = client.document(f"positions/{trading_mode}/latest_portfolio").get()
    if not doc.exists:
        raise RuntimeError(f"positions/{trading_mode}/latest_portfolio document not found.")
    return doc.to_dict() or {}


def load_intent_snapshot(client: firestore.Client, strategy_id: str) -> Optional[Dict]:
    doc = (
        client.collection("strategies")
        .document(strategy_id)
        .collection("intent")
        .document("latest")
        .get()
    )
    if doc.exists:
        return doc.to_dict() or {}
    return None


def calculate_deployable_capital(
    net_liquidation: float,
    overall_pct: float,
    strategy_weight: float,
) -> float:
    return net_liquidation * overall_pct * strategy_weight


def format_currency(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.2f}"


def describe_strategy(
    strategy_id: str,
    exposure_cfg: Dict,
    portfolio: Dict,
    intent: Optional[Dict],
) -> Dict:
    overall_pct = float(exposure_cfg.get("overall", 0.0))
    strategy_pct = float(exposure_cfg.get("strategies", {}).get(strategy_id, 0.0))
    net_liquidation = float(portfolio.get("net_liquidation", 0.0))
    deployable = calculate_deployable_capital(net_liquidation, overall_pct, strategy_pct)

    return {
        "strategy_id": strategy_id,
        "strategy_exposure_pct": strategy_pct,
        "overall_exposure_pct": overall_pct,
        "net_liquidation": net_liquidation,
        "deployable_capital": deployable,
        "intent_status": intent.get("status") if intent else "missing",
        "intent_updated_at": intent.get("updated_at") if intent else None,
        "intent_target_positions": intent.get("target_positions") if intent else [],
    }


def dump_human_readable(summary: Dict, verbose_intents: bool) -> None:
    print("\n=== Commander Exposure Summary ===")
    print(f"Project ID        : {summary['project_id']}")
    print(f"Trading Mode      : {summary['trading_mode']}")
    print(f"Snapshot Updated  : {summary['portfolio_updated_at']}")
    print(f"Net Liquidation   : {format_currency(summary['net_liquidation'])}")
    print(f"Overall Exposure  : {summary['overall_exposure_pct'] * 100:.2f}%")

    print("\n--- Strategy Breakdown ---")
    for strategy in summary["strategies"]:
        print(f"* {strategy['strategy_id']}")
        print(f"    - Strategy Exposure : {strategy['strategy_exposure_pct'] * 100:.2f}%")
        print(f"    - Deployable Capital: {format_currency(strategy['deployable_capital'])}")
        print(f"    - Intent Status     : {strategy['intent_status']} @ {strategy['intent_updated_at']}")
        if verbose_intents and strategy["intent_target_positions"]:
            print("    - Target Positions  :")
            for position in strategy["intent_target_positions"]:
                quantity = position.get("quantity")
                symbol = position.get("symbol") or position.get("contract", {}).get("symbol")
                print(f"        • {symbol} -> {quantity}")
        elif verbose_intents:
            print("    - Target Positions  : []")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Commander exposure against Firestore.")
    parser.add_argument("--project-id", required=True, help="GCP project id hosting Firestore.")
    parser.add_argument(
        "--strategies",
        nargs="+",
        required=True,
        help="One or more strategy identifiers to verify (e.g. spy_macd_vixy).",
    )
    parser.add_argument(
        "--trading-mode",
        default="paper",
        help="Portfolio document namespace (default: paper).",
    )
    parser.add_argument(
        "--show-intents",
        action="store_true",
        help="Print target_positions for each strategy intent.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable output.",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    client = firestore.Client(project=args.project_id)

    config = load_common_config(client)
    exposure_cfg = config.get("exposure", {})
    portfolio = load_portfolio_snapshot(client, args.trading_mode)

    strategies_summary = []
    for strategy_id in args.strategies:
        intent = load_intent_snapshot(client, strategy_id)
        strategies_summary.append(describe_strategy(strategy_id, exposure_cfg, portfolio, intent))

    summary = {
        "project_id": args.project_id,
        "trading_mode": args.trading_mode,
        "portfolio_updated_at": portfolio.get("updated_at"),
        "net_liquidation": float(portfolio.get("net_liquidation", 0.0)),
        "overall_exposure_pct": float(exposure_cfg.get("overall", 0.0)),
        "strategies": strategies_summary,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        dump_human_readable(summary, args.show_intents)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
