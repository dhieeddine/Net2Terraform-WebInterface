from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _terraform_output_value(outputs: Dict[str, Any], key: str, default: Any = None) -> Any:
    value = outputs.get(key, default)

    if isinstance(value, dict) and "value" in value:
        return value.get("value", default)

    return value


def _normalize_pem_path(pem_file: str) -> str:
    """
    inventory.ini is generated inside generated/ansible/.
    Terraform writes PEM files inside generated/.

    So inventory must reference ../PC3.pem, ../PC1.pem, etc.
    """
    pem_file = str(pem_file)

    if pem_file.startswith("/") or pem_file.startswith("../"):
        return pem_file

    return f"../{pem_file}"


def render_inventory(
    architecture: Dict[str, Any],
    ansible_plan: Dict[str, Any],
    terraform_outputs: Optional[Dict[str, Any]] = None,
) -> str:
    terraform_outputs = terraform_outputs or {}

    lines = ["[net2tf_targets]"]

    target_hosts = ansible_plan.get("target_hosts", [])

    for host in target_hosts:
        host = str(host)
        key = host.lower()

        ansible_host = (
            _terraform_output_value(terraform_outputs, f"{key}_public_ip")
            or _terraform_output_value(terraform_outputs, f"{key}_private_ip")
            or f"CHANGE_ME_{host}_IP"
        )

        pem_file = _terraform_output_value(
            terraform_outputs,
            f"{key}_pem_file",
            f"{host}.pem",
        )

        pem_file = _normalize_pem_path(pem_file)

        lines.append(
            f"{host} "
            f"ansible_host={ansible_host} "
            f"ansible_user=ec2-user "
            f"ansible_ssh_private_key_file={pem_file} "
            f"ansible_python_interpreter=/usr/bin/python3"
        )

    lines.extend(
        [
            "",
            "[all:vars]",
            "ansible_host_key_checking=False",
            "",
        ]
    )

    return "\n".join(lines)


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'

    if isinstance(value, bool):
        return "true" if value else "false"

    text = str(value)
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_playbook(ansible_plan: Dict[str, Any]) -> str:
    target_hosts = ansible_plan.get("target_hosts", [])
    become = bool(ansible_plan.get("become", True))
    tasks = ansible_plan.get("tasks", [])

    hosts_expr = ",".join(str(h) for h in target_hosts) if target_hosts else "net2tf_targets"

    lines = [
        "---",
        "- name: Configure net2tf generated infrastructure",
        f"  hosts: {hosts_expr}",
        f"  become: {'true' if become else 'false'}",
        "  tasks:",
    ]

    if not tasks:
        lines.extend(
            [
                "    - name: No requested tasks",
                "      ansible.builtin.debug:",
                '        msg: "No Ansible tasks were requested."',
            ]
        )
        return "\n".join(lines) + "\n"

    for task in tasks:
        task_type = task.get("type")
        task_name = task.get("name") or task_type or "Run task"

        lines.append(f"    - name: {task_name}")

        if task_type == "install_packages":
            packages = task.get("packages") or []
            lines.append("      ansible.builtin.package:")
            lines.append("        name:")
            for package in packages:
                lines.append(f"          - {package}")
            lines.append("        state: present")

        elif task_type == "start_service":
            service = task.get("service")
            lines.append("      ansible.builtin.service:")
            lines.append(f"        name: {service}")
            lines.append("        state: started")

        elif task_type == "enable_service":
            service = task.get("service")
            lines.append("      ansible.builtin.service:")
            lines.append(f"        name: {service}")
            lines.append("        enabled: true")

        elif task_type == "restart_service":
            service = task.get("service")
            lines.append("      ansible.builtin.service:")
            lines.append(f"        name: {service}")
            lines.append("        state: restarted")

        elif task_type == "run_command":
            command = task.get("command")
            lines.append("      ansible.builtin.command:")
            lines.append(f"        cmd: {_yaml_scalar(command)}")

        elif task_type == "shell":
            command = task.get("command")
            lines.append("      ansible.builtin.shell:")
            lines.append(f"        cmd: {_yaml_scalar(command)}")

        elif task_type in {"copy_file", "write_file"}:
            dest = task.get("dest")
            content = task.get("content", "")
            lines.append("      ansible.builtin.copy:")
            lines.append(f"        dest: {_yaml_scalar(dest)}")
            lines.append("        content: |")
            for content_line in str(content).splitlines() or [""]:
                lines.append(f"          {content_line}")

        else:
            lines.append("      ansible.builtin.debug:")
            lines.append(f'        msg: "Unsupported task type: {task_type}"')

    return "\n".join(lines) + "\n"


def render_ansible_cfg() -> str:
    return """[defaults]
host_key_checking = False
retry_files_enabled = False
inventory = inventory.ini
timeout = 30

[ssh_connection]
ssh_args = -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
"""


def render_readme(ansible_prompt: str, ansible_plan: Dict[str, Any]) -> str:
    notes = ansible_plan.get("notes") or []
    notes_text = "\n".join(f"- {note}" for note in notes) if notes else "- No extra notes."

    return (
        "# Generated Ansible Project\n\n"
        "This folder was generated from the user Ansible request:\n\n"
        "REQUEST:\n"
        f"{ansible_prompt}\n\n"
        "## Files\n\n"
        "- inventory.ini: generated Ansible inventory\n"
        "- playbook.yml: generated Ansible playbook\n"
        "- ansible.cfg: local Ansible configuration\n"
        "- ansible_plan.json: structured Ansible plan\n\n"
        "## Usage\n\n"
        "From this folder, run:\n\n"
        "```bash\n"
        "ansible-playbook --syntax-check playbook.yml\n"
        "ansible-playbook playbook.yml\n"
        "```\n\n"
        "## Notes\n\n"
        f"{notes_text}\n"
    )


def render_ansible_project(
    ansible_prompt: str,
    architecture: Dict[str, Any],
    ansible_plan: Dict[str, Any],
    out_dir: str,
    terraform_outputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)

    files = {
        "inventory.ini": render_inventory(
            architecture=architecture,
            ansible_plan=ansible_plan,
            terraform_outputs=terraform_outputs,
        ),
        "playbook.yml": render_playbook(ansible_plan),
        "ansible.cfg": render_ansible_cfg(),
        "README.md": render_readme(ansible_prompt, ansible_plan),
        "ansible_plan.json": json.dumps(ansible_plan, indent=2),
    }

    written = {}

    for name, content in files.items():
        path = Path(out_dir) / name
        path.write_text(content, encoding="utf-8")
        written[name] = str(path)

    return written
