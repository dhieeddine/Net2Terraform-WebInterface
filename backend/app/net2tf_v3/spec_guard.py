from __future__ import annotations

from typing import Any, Dict, List


def _as_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj

    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)

    if hasattr(obj, "dict"):
        return obj.dict(by_alias=True)

    return {}


def _component_ids(architecture: Dict[str, Any]) -> set[str]:
    return {str(c.get("id")) for c in architecture.get("components", []) or []}


def evaluate_spec_compliance(input_obj: Any) -> Dict[str, Any]:
    """
    Supports both:
    1. evaluate_spec_compliance(result)
       where result contains {"status": "ok", "architecture": {...}}

    2. evaluate_spec_compliance(architecture)
       where architecture directly contains {"components": ..., "domain_plan": ...}

    Returns both "ok" and "passed" because eval_suite.py checks "passed".
    """

    data = _as_dict(input_obj)

    # If app.py passes full result dict, architecture is nested.
    # If app.py passes architecture directly, components/domain_plan are top-level.
    if "architecture" in data and isinstance(data.get("architecture"), dict):
        status = data.get("status", "ok")
        architecture = data.get("architecture", {}) or {}
    else:
        status = "ok"
        architecture = data

    issues: List[str] = []
    warnings: List[str] = []

    if status != "ok":
        issues.append(f"Generation status is not ok: {status}")

    components = architecture.get("components", []) or []
    edges = architecture.get("edges", []) or []
    domain_plan = architecture.get("domain_plan", {}) or {}
    routers = domain_plan.get("routers", {}) or {}

    ids = _component_ids(architecture)

    if not components:
        issues.append("No components were extracted from the prompt.")

    if not edges:
        warnings.append("No edges were extracted from the prompt.")

    router_components = [
        c.get("id")
        for c in components
        if c.get("type") == "router"
    ]

    if router_components and not routers:
        issues.append("Routers were extracted but no router domain plan was produced.")

    for edge in edges:
        a = edge.get("from") or edge.get("from_")
        b = edge.get("to")

        if a not in ids:
            issues.append(f"Edge references unknown component: {a}")

        if b not in ids:
            issues.append(f"Edge references unknown component: {b}")

    for rid, router in routers.items():
        if not router.get("vpc_cidr"):
            issues.append(f"Router {rid} has no VPC CIDR.")

        if not router.get("subnets"):
            warnings.append(f"Router {rid} has no subnets.")

        for subnet in router.get("subnets", []) or []:
            if not subnet.get("cidr"):
                issues.append(f"Router {rid} subnet {subnet.get('name')} has no CIDR.")

            for hp in subnet.get("host_placements", []) or []:
                host_id = hp.get("host_id")
                if host_id and host_id not in ids:
                    issues.append(f"Subnet {subnet.get('name')} references unknown host: {host_id}")

    passed = len(issues) == 0

    return {
        "ok": passed,
        "passed": passed,
        "issues": issues,
        "warnings": warnings,
        "summary": {
            "component_count": len(components),
            "edge_count": len(edges),
            "router_count": len(routers),
            "connectivity_mode": domain_plan.get("connectivity_mode", "none"),
        },
    }
