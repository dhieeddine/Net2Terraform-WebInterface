from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .app import compile_prompt


SNAPSHOT_CASES: List[Dict[str, Any]] = [
    {
        "name": "single_router_basic_snapshot",
        "prompt": """I have one router R1 with 1 interface, one switch SW1, and one PC PC1.
PC1 is connected to SW1.
SW1 is connected to R1.
base cidr 10.0.0.0/16
SW1 = 10.0.1.0/29""",
        "expected_snapshot": {
            "connectivity_mode": "none",
            "routers": {
                "R1": {
                    "vpc_cidr": "10.0.0.0/16",
                    "subnets": [
                        {
                            "name": "SW1",
                            "cidr": "10.0.1.0/29",
                            "public": False,
                            "needs_nat": False,
                            "hosts": [
                                {
                                    "host_id": "PC1",
                                    "private_ip": "10.0.1.4",
                                    "exposure": "private",
                                    "is_bastion": False,
                                }
                            ],
                        }
                    ],
                }
            },
        },
    }
]


def simplify_architecture(architecture: Dict[str, Any]) -> Dict[str, Any]:
    domain_plan = architecture.get("domain_plan", {}) or {}
    routers = domain_plan.get("routers", {}) or {}

    out = {
        "connectivity_mode": domain_plan.get("connectivity_mode"),
        "routers": {},
    }

    for rid, router in routers.items():
        simple_router = {
            "vpc_cidr": router.get("vpc_cidr"),
            "subnets": [],
        }

        for subnet in router.get("subnets", []) or []:
            simple_subnet = {
                "name": subnet.get("name"),
                "cidr": subnet.get("cidr"),
                "public": subnet.get("public"),
                "needs_nat": subnet.get("needs_nat"),
                "hosts": [],
            }

            for hp in subnet.get("host_placements", []) or []:
                simple_subnet["hosts"].append(
                    {
                        "host_id": hp.get("host_id"),
                        "private_ip": hp.get("private_ip"),
                        "exposure": hp.get("exposure"),
                        "is_bastion": hp.get("is_bastion"),
                    }
                )

            simple_router["subnets"].append(simple_subnet)

        out["routers"][rid] = simple_router

    return out


def compare_values(expected: Any, actual: Any, path: str = "") -> List[str]:
    mismatches: List[str] = []

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or 'root'}: expected dict, got {type(actual).__name__}"]
        for key, expected_value in expected.items():
            next_path = f"{path}.{key}" if path else key
            if key not in actual:
                mismatches.append(f"{next_path}: missing in actual")
                continue
            mismatches.extend(compare_values(expected_value, actual[key], next_path))
        return mismatches

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path or 'root'}: expected list, got {type(actual).__name__}"]
        if len(expected) != len(actual):
            mismatches.append(f"{path}: expected list length {len(expected)}, got {len(actual)}")
            return mismatches
        for i, (ev, av) in enumerate(zip(expected, actual)):
            mismatches.extend(compare_values(ev, av, f"{path}[{i}]"))
        return mismatches

    if expected != actual:
        mismatches.append(f"{path}: expected {expected!r}, got {actual!r}")

    return mismatches


def evaluate_snapshot_case(case: Dict[str, Any], out_root: str) -> Dict[str, Any]:
    case_name = case["name"]
    out_dir = str(Path(out_root) / case_name)

    result = compile_prompt(case["prompt"], out_dir=out_dir)

    if result.get("status") != "ok":
        return {
            "name": case_name,
            "passed": False,
            "reason": f"compile_prompt returned status={result.get('status')!r}",
        }

    actual_snapshot = simplify_architecture(result["architecture"])
    expected_snapshot = case["expected_snapshot"]
    mismatches = compare_values(expected_snapshot, actual_snapshot)

    return {
        "name": case_name,
        "passed": len(mismatches) == 0,
        "mismatches": mismatches,
    }


def run_snapshot_suite(out_root: str = "./snapshot_runs") -> Dict[str, Any]:
    os.makedirs(out_root, exist_ok=True)

    results = [evaluate_snapshot_case(case, out_root=out_root) for case in SNAPSHOT_CASES]
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
    report = run_snapshot_suite()
    print(json.dumps(report, indent=2))
