import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException

from ..core.config import VISION_LLM_PROVIDERS
from .llm_gateway import llm_gateway

logger = logging.getLogger("uvicorn.error")

def strip_markdown_fences(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\\s*", "", cleaned)
    cleaned = re.sub(r"\\s*```$", "", cleaned)
    return cleaned.strip()


def extract_message_content(message_content: Any) -> str:
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        parts: list[str] = []
        for part in message_content:
            if isinstance(part, dict):
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif isinstance(part.get("content"), str):
                    parts.append(part["content"])
            elif isinstance(part, str):
                parts.append(part)
        return "\\n".join(parts)
    return ""


async def call_openrouter(
    image_b64: str,
    mime_type: str,
    yolo_hints: list[str],
    topology_links: list[tuple[str, str]],
    node_name_hints: dict[str, str] | None = None,
) -> str:
    hints_string = ", ".join(yolo_hints) if yolo_hints else "none"
    links_string = (
        ", ".join(f"{from_id}<->{to_id}" for from_id, to_id in topology_links)
        if topology_links
        else "none"
    )
    name_hints_string = (
        ", ".join(f"{node_id}={name}" for node_id, name in (node_name_hints or {}).items())
        if node_name_hints
        else "none"
    )
    
    logger.info(
        "[LLM] Request start detections=%s links=%s ocr_names=%s image_b64_chars=%d",
        hints_string,
        links_string,
        name_hints_string,
        len(image_b64),
    )
    
    prompt = (
        "Act as a Senior AWS Architect.\n"
        f"YOLO detected these components: {hints_string}.\n"
        f"Detected topology links (authoritative): {links_string}.\n"
        f"Detected OCR object names by node id: {name_hints_string}.\n"
        "Use these links as source-of-truth for connectivity and routing relationships.\n"
        "If OCR names are provided, use them to name Terraform resources and Name tags.\n"
        "Sanitize OCR names for Terraform identifiers (lowercase, letters/digits/underscore only).\n"
        "Generate a valid AWS Terraform main.tf file from the uploaded topology image.\n"
        "Terraform rules: VPC 10.0.0.0/16, Router->IGW+Route Tables, Switch->Subnet, PC->aws_instance t3.micro.\n"
        "Output ONLY raw HCL code (no markdown, no explanations)."
    )
    
    if not image_b64 or len(image_b64) == 0:
        logger.error("Image base64 data is empty")
        raise HTTPException(status_code=400, detail="Image data is empty")

    provider_order = [p.strip() for p in VISION_LLM_PROVIDERS.split(",") if p.strip()]

    try:
        raw_content = await llm_gateway.generate_vision(
            prompt=prompt,
            image_b64=image_b64,
            mime_type=mime_type,
            providers=provider_order,
            temperature=0.1,
        )
        result = strip_markdown_fences(raw_content)
        logger.info("Generated code length: %d characters", len(result))
        return result
    except Exception as e:
        logger.error("All configured vision providers failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=f"Vision LLM providers failed: {e}")
