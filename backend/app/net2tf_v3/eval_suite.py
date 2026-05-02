from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .app import compile_prompt


TEST_CASES: List[Dict[str, Any]] = [
    {
        "name": "single_router_basic",
        "prompt": """I have one router R1 with 1 interface, one switch SW1, and one PC PC1.
PC1 is connected to SW1.
SW1 is connected to R1.
base cidr 10.0.0.0/16
SW1 = 10.0.1.0/29""",
        "expected": {
            "connectivity_mode": "none",
            "public_private_strategy": "single_subnet",
            "nat_required": False,
            "bastion_required": False,
        },
    },
    {
        "name": "public_private_nat_bastion",
        "prompt": """I have one router R1 with 1 interface, one switch SW1, one PC PC1, and one server S1.
PC1 is connected to SW1.
S1 is connected to SW1.
SW1 is connected to R1.
PC1 should be the bastion.
S1 should be private but needs internet access.
base cidr 10.0.0.0/16
SW1 = 10.0.1.0/27
firewall mode is sg""",
        "expected": {
            "connectivity_mode": "none",
            "public_private_strategy": "split_public_private",
            "nat_required": True,
            "bastion_required": True,
        },
    },
    {
        "name": "two_router_peering",
        "prompt": """I have one router R1 with 1 interface, one router R2 with 1 interface, one switch SW1, one switch SW2, one PC PC1, and one PC PC2.
PC1 is connected to SW1.
SW1 is connected to R1.
R1 is connected to R2.
R2 is connected to SW2.
SW2 is connected to PC2.
base cidr 10.0.0.0/8
SW1 = 10.0.1.0/29
SW2 = 10.1.1.0/29
firewall mode is sg""",
        "expected": {
            "connectivity_mode": "peering",
            "public_private_strategy": "multi_vpc_peering",
            "nat_required": False,
            "bastion_required": False,
        },
    },
    {
        "name": "three_router_tgw",
        "prompt": """I have one router R1 with 1 interface, one router R2 with 1 interface, one router R3 with 1 interface, one switch SW1, one switch SW2, one PC PC1, and one PC PC2.
PC1 is connected to SW1.
SW1 is connected to R1.
R1 is connected to R2.
R2 is connected to R3.
R3 is connected to SW2.
SW2 is connected to PC2.
base cidr 10.0.0.0/8
SW1 = 10.0.1.0/29
SW2 = 10.2.1.0/29
firewall mode is sg""",
        "expected": {
            "connectivity_mode": "tgw",
            "public_private_strategy": "multi_vpc_tgw",
            "nat_required": False,
            "bastion_required": False,
        },
    },
    {
        "name": "firewall_defaults_to_sg",
        "prompt": """I have one router R1 with 1 interface, one switch SW1, one PC PC1, one server S1, and one firewall FW1.
PC1 is connected to SW1.
S1 is connected to SW1.
SW1 is connected to R1.
PC1 should be the bastion.
S1 should be private but needs internet access.
base cidr 10.0.0.0/16
SW1 = 10.0.1.0/27""",
        "expected": {
            "connectivity_mode": "none",
            "public_private_strategy": "split_public_private",
            "nat_required": True,
            "bastion_required": True,
        },
    },
]


def evaluate_case(case: Dict[str, Any], out_root: str) -> Dict[str, Any]:
    case_name = case["name"]
    out_dir = str(Path(out_root) / case_name)

    result = compile_prompt(case["prompt"], out_dir=out_dir)

    rag_plan = result.get("rag_plan", {})
    plan_guard = result.get("plan_guard", {})
    quality = result.get("quality_checks", {})
    architecture = result.get("architecture", {}) or {}
    spec_guard = result.get("spec_guard", {}) or {}
    expected = case["expected"]

    firewall_mode = ((architecture.get("firewall_policy", {}) or {}).get("mode"))

    checks = {
        "status_ok": result.get("status") == "ok",
        "connectivity_mode": rag_plan.get("connectivity_mode") == expected["connectivity_mode"],
        "public_private_strategy": rag_plan.get("public_private_strategy") == expected["public_private_strategy"],
        "nat_required": rag_plan.get("nat_required") == expected["nat_required"],
        "bastion_required": rag_plan.get("bastion_required") == expected["bastion_required"],
        "plan_guard_matches": plan_guard.get("matches") is True,
        "terraform_validate_ok": quality.get("validate_ok") is True,
        "spec_guard_passed": spec_guard.get("passed") is True,
    }

    if case_name == "firewall_defaults_to_sg":
        checks["firewall_mode_defaulted_to_sg"] = firewall_mode == "sg"

    passed = all(checks.values())

    return {
        "name": case_name,
        "passed": passed,
        "checks": checks,
        "expected": expected,
        "actual_rag_plan": {
            "connectivity_mode": rag_plan.get("connectivity_mode"),
            "public_private_strategy": rag_plan.get("public_private_strategy"),
            "nat_required": rag_plan.get("nat_required"),
            "bastion_required": rag_plan.get("bastion_required"),
        },
        "actual_firewall_mode": firewall_mode,
    }


def run_suite(out_root: str = "./eval_runs") -> Dict[str, Any]:
    os.makedirs(out_root, exist_ok=True)
    results = [evaluate_case(case, out_root=out_root) for case in TEST_CASES]
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
    report = run_suite()
    print(json.dumps(report, indent=2))
