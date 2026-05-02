from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _to_dict(obj: Any) -> Dict[str, Any]:
    """
    Convert a Pydantic model or dict into a plain dict.
    """
    if isinstance(obj, dict):
        return obj

    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True)

    if hasattr(obj, "dict"):
        return obj.dict(by_alias=True)

    raise TypeError(f"Unsupported architecture type: {type(obj).__name__}")


def _build_context(architecture: Any) -> Dict[str, Any]:
    """
    Build a Jinja context that supports all template variable styles.

    This avoids errors like:
    - 'architecture' is undefined
    - 'connectivity_mode' is undefined
    """
    arch = _to_dict(architecture)

    domain_plan = arch.get("domain_plan", {}) or {}
    routers = domain_plan.get("routers", {}) or {}
    router_links = domain_plan.get("router_links", []) or []
    connectivity_mode = domain_plan.get("connectivity_mode", "none") or "none"

    return {
        # Full architecture aliases
        "architecture": arch,
        "arch": arch,

        # Domain-plan aliases
        "domain_plan": domain_plan,
        "routers": routers,
        "router_links": router_links,
        "connectivity_mode": connectivity_mode,

        # Other architecture sections
        "components": arch.get("components", []) or [],
        "edges": arch.get("edges", []) or [],
        "addressing": arch.get("addressing", {}) or {},
        "firewall_policy": arch.get("firewall_policy", {}) or {},
        "user_policies": arch.get("user_policies", {}) or {},
    }


def _render_template(env: Environment, template_name: str, context: Dict[str, Any]) -> str:
    template = env.get_template(template_name)
    return template.render(**context)


def render_project(
    architecture: Any,
    templates_dir: str,
    out_dir: str,
) -> Dict[str, str]:
    """
    Render Terraform project files from Jinja templates.
    """
    templates_path = Path(templates_dir)
    output_path = Path(out_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(templates_path)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    context = _build_context(architecture)

    template_to_output = {
        "main.tf.j2": "main.tf",
        "variables.tf.j2": "variables.tf",
        "outputs.tf.j2": "outputs.tf",
        "terraform.tfvars.example.j2": "terraform.tfvars.example",
        "README.md.j2": "README.md",
    }

    written: Dict[str, str] = {}

    for template_name, output_name in template_to_output.items():
        template_file = templates_path / template_name

        if not template_file.exists():
            continue

        rendered = _render_template(env, template_name, context)

        out_file = output_path / output_name
        out_file.write_text(rendered, encoding="utf-8")

        written[output_name] = str(out_file)

    return written
