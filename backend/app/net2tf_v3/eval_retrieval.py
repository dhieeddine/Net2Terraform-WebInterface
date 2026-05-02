from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .retriever import retrieve_context, get_retriever_device


RETRIEVAL_CASES: List[Dict] = [
    {
        "name": "bastion_nat_case",
        "query": "PC1 should be the bastion. S1 should be private but needs internet access.",
        "must_have_in_top3": ["bastion.md", "nat.md"],
        "should_not_be_top1": ["peering.md", "tgw.md"],
    },
    {
        "name": "single_router_case",
        "query": "I have one router R1, one switch SW1, and one PC PC1 connected through SW1.",
        "must_have_in_top3": ["single_router.md"],
        "should_not_be_top1": ["peering.md", "tgw.md"],
    },
    {
        "name": "peering_case",
        "query": "R1 is connected to R2. PC1 is behind R1 and PC2 is behind R2.",
        "must_have_in_top3": ["peering.md"],
        "should_not_be_top1": ["tgw.md"],
    },
    {
        "name": "tgw_case",
        "query": "R1 is connected to R2. R2 is connected to R3. Use a routed cloud topology.",
        "must_have_in_top3": ["tgw.md", "aws_network_patterns.md"],
        "should_not_be_top1": ["peering.md"],
    },
]


def evaluate_case(case: Dict) -> Dict:
    retrieved = retrieve_context(case["query"], top_k=6)
    retrieved_sources = [Path(x["source"]).name for x in retrieved]

    top1 = retrieved_sources[:1]
    top3 = retrieved_sources[:3]

    must_have = case["must_have_in_top3"]
    should_not_be_top1 = case["should_not_be_top1"]

    must_have_ok = all(any(src == got for got in top3) for src in must_have)
    top1_ok = all(bad not in top1 for bad in should_not_be_top1)

    passed = must_have_ok and top1_ok

    return {
        "name": case["name"],
        "passed": passed,
        "query": case["query"],
        "top1_source": top1[0] if top1 else None,
        "top3_sources": top3,
        "must_have_ok": must_have_ok,
        "top1_ok": top1_ok,
    }


def run_suite() -> Dict:
    results = [evaluate_case(case) for case in RETRIEVAL_CASES]
    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "device": get_retriever_device(),
        },
        "results": results,
    }


if __name__ == "__main__":
    report = run_suite()
    print(json.dumps(report, indent=2))
