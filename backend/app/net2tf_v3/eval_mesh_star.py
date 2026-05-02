from __future__ import annotations

import json
from typing import Any, Dict, List

from .app import compile_prompt
from .spec_guard import evaluate_spec_compliance


MESH_STAR_CASES: List[Dict[str, Any]] = [
    {
        "name": "triangle_mesh",
        "prompt": """I have three routers R1, R2, and R3.
R1 is connected to R2.
R1 is connected to R3.
R2 is connected to R3.
I have one switch SW1 and one PC PC1 behind R1.
I have one switch SW2 and one PC PC2 behind R2.
I have one switch SW3 and one PC PC3 behind R3.
PC1 is connected to SW1.
SW1 is connected to R1.
PC2 is connected to SW2.
SW2 is connected to R2.
PC3 is connected to SW3.
SW3 is connected to R3.
base cidr 10.0.0.0/8
SW1 = 10.0.1.0/29
SW2 = 10.1.1.0/29
SW3 = 10.2.1.0/29
firewall mode is sg""",
        "expect_status": "ok",
        "expect_connectivity_mode": "tgw",
    }
]


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    result = compile_prompt(case["prompt"], out_dir=f"./mesh_star_runs/{case['name']}")
    actual_status = result.get("status")
    passed = actual_status == case["expect_status"]

    if actual_status != "ok":
        return {"name": case["name"], "passed": passed, "actual_status": actual_status}

    architecture = result.get("architecture", {}) or {}
    domain_plan = architecture.get("domain_plan", {}) or {}
    connectivity_mode = domain_plan.get("connectivity_mode")

    spec_report = evaluate_spec_compliance(result)

    passed = passed and (connectivity_mode == case["expect_connectivity_mode"]) and spec_report["passed"]

    return {
        "name": case["name"],
        "passed": passed,
        "actual_status": actual_status,
        "connectivity_mode": connectivity_mode,
        "spec_report_passed": spec_report["passed"],
    }


def run_suite() -> Dict[str, Any]:
    results = [evaluate_case(case) for case in MESH_STAR_CASES]
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
