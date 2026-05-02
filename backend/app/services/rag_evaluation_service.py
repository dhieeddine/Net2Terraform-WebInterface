"""
RAG Evaluation Service - extracted from final-rag.ipynb
Provides functions for RAG-based Terraform generation testing and evaluation.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path


class RAGEvaluationService:
    """Service for RAG and LLM result evaluation."""

    def __init__(self):
        self.test_cases = self._load_test_cases()
        self.results_history = []

    def _load_test_cases(self) -> List[Dict[str, Any]]:
        """Load predefined test cases from the notebook evaluation suite."""
        return [
            {
                "name": "01_easy_auto_single_router",
                "description": "Single router with automatic addressing",
                "prompt": """
I have router R1, switch SW1, and PC1.

PC1 is connected to SW1.
SW1 is connected to R1.

There is only one router and one LAN.
No NAT is required.
No bastion is required.
No firewall is required.

Automatic addressing is allowed.
do it by yourself
""",
                "expected_properties": {
                    "connectivity_mode": "none",
                    "nat_required": False,
                    "firewall_mode": None,
                }
            },
            {
                "name": "02_easy_manual_single_router",
                "description": "Single router with manual addressing",
                "prompt": """
I have router R1, switch SW1, PC1, and server S1.

PC1 is connected to SW1.
S1 is connected to SW1.
SW1 is connected to R1.

base cidr 10.0.0.0/16
SW1 = 10.0.1.0/27

Both PC1 and S1 can stay private.
No NAT is required.
do it by yourself
""",
                "expected_properties": {
                    "connectivity_mode": "none",
                    "nat_required": False,
                }
            },
            {
                "name": "03_public_private_nat",
                "description": "Public and private subnets with NAT",
                "prompt": """
I have router R1, switch SW1, PC1, and server S1.

PC1 is connected to SW1.
S1 is connected to SW1.
SW1 is connected to R1.

base cidr 10.0.0.0/16
SW1 = 10.0.1.0/27

PC1 should be public.
S1 should be private but needs outbound internet access.

Split SW1 into a public subnet and a private subnet.
Create an internet gateway for the public subnet.
Create a NAT gateway for the private subnet.

do it by yourself
""",
                "expected_properties": {
                    "connectivity_mode": "none",
                    "nat_required": True,
                }
            },
            {
                "name": "04_two_router_peering",
                "description": "Two routers with VPC peering",
                "prompt": """
I have router R1, router R2, switch SW1, switch SW2, PC1, PC2, server S1, and server S2.

PC1 is connected to SW1.
S1 is connected to SW1.
SW1 is connected to R1.

PC2 is connected to SW2.
S2 is connected to SW2.
SW2 is connected to R2.

R1 is connected to R2.

base cidr 10.0.0.0/8
SW1 = 10.0.1.0/27
SW2 = 10.1.1.0/27

Use VPC peering between the two VPCs.
No NAT is required.
do it by yourself
""",
                "expected_properties": {
                    "connectivity_mode": "peering",
                    "nat_required": False,
                }
            },
            {
                "name": "05_three_router_tgw",
                "description": "Three routers with Transit Gateway",
                "prompt": """
I have router R1, router R2, router R3, switch SW1, switch SW2, switch SW3, PC1, PC2, and PC3.

PC1 is connected to SW1.
SW1 is connected to R1.

PC2 is connected to SW2.
SW2 is connected to R2.

PC3 is connected to SW3.
SW3 is connected to R3.

R1 is connected to R2.
R2 is connected to R3.

base cidr 10.0.0.0/8
SW1 = 10.0.1.0/27
SW2 = 10.1.1.0/27
SW3 = 10.2.1.0/27

Use Transit Gateway for inter-router connectivity.
do it by yourself
""",
                "expected_properties": {
                    "connectivity_mode": "tgw",
                    "nat_required": False,
                }
            }
        ]

    def get_test_cases(self) -> List[Dict[str, Any]]:
        """Return list of all available test cases."""
        return self.test_cases

    def get_test_case(self, test_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific test case by name."""
        for test in self.test_cases:
            if test["name"] == test_name:
                return test
        return None

    def evaluate_result(self, result: Dict[str, Any], test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a generation result against expected properties.

        Args:
            result: Generated result from compile_prompt or similar
            test_case: Test case definition with expected properties

        Returns:
            Evaluation report with pass/fail status and details
        """
        evaluation = {
            "test_name": test_case.get("name"),
            "timestamp": datetime.now().isoformat(),
            "passed": True,
            "checks": {},
            "issues": [],
            "metrics": {}
        }

        # Check status
        status = result.get("status")
        evaluation["checks"]["status"] = status == "ok"
        if status != "ok":
            evaluation["issues"].append(f"Generation failed with status: {status}")
            evaluation["passed"] = False

        # Check main.tf exists
        main_tf = result.get("main_tf_content", "")
        evaluation["checks"]["main_tf_exists"] = bool(main_tf)
        if not main_tf:
            evaluation["issues"].append("No main.tf generated")
            evaluation["passed"] = False

        # Check expected properties
        expected = test_case.get("expected_properties", {})
        rag_plan = result.get("rag_plan", {})
        architecture = result.get("architecture", {})

        for prop_name, expected_value in expected.items():
            if prop_name == "connectivity_mode":
                actual = rag_plan.get("connectivity_mode")
                check_passed = actual == expected_value
                evaluation["checks"][prop_name] = check_passed
                if not check_passed:
                    evaluation["issues"].append(
                        f"Connectivity mode mismatch: expected={expected_value}, actual={actual}"
                    )
                    evaluation["passed"] = False

            elif prop_name == "nat_required":
                actual = rag_plan.get("nat_required")
                check_passed = actual == expected_value
                evaluation["checks"][prop_name] = check_passed
                if not check_passed:
                    evaluation["issues"].append(
                        f"NAT requirement mismatch: expected={expected_value}, actual={actual}"
                    )
                    evaluation["passed"] = False

            elif prop_name == "firewall_mode":
                firewall_policy = architecture.get("firewall_policy", {})
                actual = firewall_policy.get("mode")
                check_passed = actual == expected_value
                evaluation["checks"][prop_name] = check_passed
                if not check_passed and expected_value is not None:
                    evaluation["issues"].append(
                        f"Firewall mode mismatch: expected={expected_value}, actual={actual}"
                    )
                    evaluation["passed"] = False

        # Check Terraform quality
        if main_tf:
            evaluation["checks"]["no_29_subnets"] = "/29" not in main_tf
            evaluation["checks"]["uses_key_name_prefix"] = "key_name_prefix" in main_tf
            evaluation["checks"]["no_inline_route_blocks"] = "route {" not in main_tf

            # Connectivity mode specific checks
            connectivity_mode = rag_plan.get("connectivity_mode")
            if connectivity_mode == "tgw":
                evaluation["checks"]["has_tgw"] = "aws_ec2_transit_gateway" in main_tf
                evaluation["checks"]["tgw_default_assoc_disabled"] = (
                    'default_route_table_association = "disable"' in main_tf
                )

            elif connectivity_mode == "peering":
                evaluation["checks"]["has_peering"] = "aws_vpc_peering_connection" in main_tf

            if rag_plan.get("nat_required"):
                evaluation["checks"]["has_nat_gateway"] = "aws_nat_gateway" in main_tf

            # Count quality checks
            check_results = evaluation["checks"]
            evaluation["metrics"]["total_checks"] = len(check_results)
            evaluation["metrics"]["passed_checks"] = sum(1 for v in check_results.values() if v)
            evaluation["metrics"]["check_pass_rate"] = (
                evaluation["metrics"]["passed_checks"] / evaluation["metrics"]["total_checks"]
                if evaluation["metrics"]["total_checks"] > 0 else 0
            )

        # Store in history
        self.results_history.append(evaluation)

        return evaluation

    def get_evaluation_summary(self) -> Dict[str, Any]:
        """Get summary statistics of all evaluations run."""
        if not self.results_history:
            return {"total_evals": 0, "passed": 0, "failed": 0, "pass_rate": 0}

        total = len(self.results_history)
        passed = sum(1 for e in self.results_history if e.get("passed"))

        return {
            "total_evals": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total > 0 else 0,
            "recent_results": self.results_history[-5:]  # Last 5 evaluations
        }

    def reset_history(self) -> None:
        """Clear evaluation history."""
        self.results_history = []


# Singleton instance
rag_evaluation_service = RAGEvaluationService()