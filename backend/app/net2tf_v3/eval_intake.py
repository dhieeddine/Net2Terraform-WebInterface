from __future__ import annotations

import json
from typing import Any, Dict, List

from .app import compile_intake_session
from .interactive_intake import process_intake_turn, start_intake_session


INTAKE_CASES: List[Dict[str, Any]] = [
    {
        "name": "auto_addressing_single_router",
        "turns": [
            "router R1 with 1 interface, switch SW1, pc PC1",
            "PC1 is connected to SW1. SW1 is connected to R1.",
            "",
            "",
        ],
        "expect_ready": True,
        "expect_status": "ok",
    },
    {
        "name": "manual_addressing_two_switches",
        "turns": [
            "router R1 with 2 interfaces, switch SW1, switch SW2, pc PC1, server S1",
            "PC1 is connected to SW1. SW1 is connected to R1.",
            "S1 is connected to SW2. SW2 is connected to R1.",
            "yes",
            "10.0.0.0/16",
            "SW1 = 10.0.1.0/24",
            "SW2 = 10.0.2.0/24",
            "",
        ],
        "expect_ready": True,
        "expect_status": "ok",
    },
    {
        "name": "missing_edge_block_then_fix",
        "turns": [
            "router R1 with 1 interface, switch SW1, pc PC1, server S1",
            "PC1 is connected to SW1. SW1 is connected to R1.",
            "S1 is connected to SW1.",
            "",
            "",
        ],
        "expect_ready": True,
        "expect_status": "ok",
    },
    {
        "name": "firewall_default_sg_should_not_block",
        "turns": [
            "router R1 with 1 interface, switch SW1, pc PC1, server S1, firewall FW1",
            "PC1 is connected to SW1. S1 is connected to SW1. SW1 is connected to R1.",
            "yes",
            "10.0.0.0/16",
            "SW1 = 10.0.1.0/27",
            "",
        ],
        "expect_ready": True,
        "expect_status": "ok",
    },
]


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    session = start_intake_session()
    history = []

    for turn in case["turns"]:
        decision = process_intake_turn(session, turn)
        history.append(
            {
                "user": turn,
                "stage": session.stage,
                "question": decision.question,
                "ready_to_compile": decision.ready_to_compile,
                "blocking_issues": list(decision.blocking_issues),
            }
        )

    ready_ok = session.ready_to_compile == case["expect_ready"]
    if not session.ready_to_compile:
        return {
            "name": case["name"],
            "passed": False,
            "reason": "session not ready to compile",
            "history": history,
        }

    result = compile_intake_session(session, out_dir=f"./intake_eval_runs/{case['name']}")
    status_ok = result.get("status") == case["expect_status"]

    return {
        "name": case["name"],
        "passed": ready_ok and status_ok,
        "expected_status": case["expect_status"],
        "actual_status": result.get("status"),
        "history": history,
    }


def run_suite() -> Dict[str, Any]:
    results = [evaluate_case(case) for case in INTAKE_CASES]
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
        "results": results,
    }


if __name__ == "__main__":
    print(json.dumps(run_suite(), indent=2))
