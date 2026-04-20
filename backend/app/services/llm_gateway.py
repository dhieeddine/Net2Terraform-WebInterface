import logging
from typing import Any, Iterable

import httpx
from google import genai

from ..core.config import (
    CHAT_LLM_PROVIDERS,
    GEMINI_MODEL_NAME,
    GOOGLE_API_KEY,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL_NAME,
    OPENROUTER_URL,
    OXLO_API_KEY,
    OXLO_MODEL_NAME,
    OXLO_URL,
    VISION_LLM_PROVIDERS,
)

logger = logging.getLogger("uvicorn.error")


class LLMGateway:
    def __init__(self):
        self._google_client = None

    @staticmethod
    def _parse_providers(raw: str) -> list[str]:
        return [p.strip().lower() for p in raw.split(",") if p.strip()]

    @staticmethod
    def _extract_message_content(message_content: Any) -> str:
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
            return "\n".join(parts)
        return ""

    def _iter_providers(self, providers: Iterable[str] | None, default_raw: str) -> list[str]:
        if providers is None:
            return self._parse_providers(default_raw)
        return [p.strip().lower() for p in providers if p and p.strip()]

    def _get_google_client(self):
        if not GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY/GEMINI_API_KEY is not set")
        if self._google_client is None:
            self._google_client = genai.Client(api_key=GOOGLE_API_KEY)
        return self._google_client

    @staticmethod
    def _provider_http_config(provider: str) -> tuple[str, str, str]:
        if provider == "openrouter":
            return OPENROUTER_API_KEY, OPENROUTER_URL, OPENROUTER_MODEL_NAME
        if provider == "oxlo":
            return OXLO_API_KEY, OXLO_URL, OXLO_MODEL_NAME
        raise ValueError(f"Unsupported HTTP provider: {provider}")

    def _generate_http_text(self, provider: str, prompt: str, temperature: float) -> str:
        api_key, url, model_name = self._provider_http_config(provider)
        if not api_key:
            raise ValueError(f"{provider.upper()} API key is not set")

        payload = {
            "model": model_name,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=60) as client:
            response = client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            detail = response.text[:300] if response.text else "No response body"
            raise RuntimeError(f"{provider} text call failed ({response.status_code}): {detail}")

        body = response.json()
        return self._extract_message_content(
            body.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

    async def _generate_http_vision(
        self,
        provider: str,
        prompt: str,
        image_b64: str,
        mime_type: str,
        temperature: float,
    ) -> str:
        api_key, url, model_name = self._provider_http_config(provider)
        if not api_key:
            raise ValueError(f"{provider.upper()} API key is not set")

        payload = {
            "model": model_name,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}",
                            },
                        },
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            detail = response.text[:300] if response.text else "No response body"
            raise RuntimeError(f"{provider} vision call failed ({response.status_code}): {detail}")

        body = response.json()
        return self._extract_message_content(
            body.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

    def generate_text(
        self,
        prompt: str,
        providers: Iterable[str] | None = None,
        temperature: float = 0.2,
    ) -> str:
        provider_order = self._iter_providers(providers, CHAT_LLM_PROVIDERS)
        errors: list[str] = []

        for provider in provider_order:
            try:
                logger.info("[LLM] text attempt provider=%s", provider)
                if provider == "google":
                    client = self._get_google_client()
                    response = client.models.generate_content(
                        model=GEMINI_MODEL_NAME,
                        contents=prompt,
                    )
                    return response.text or ""
                if provider in ("openrouter", "oxlo"):
                    return self._generate_http_text(provider, prompt, temperature)
                errors.append(f"{provider}: unsupported provider")
            except Exception as exc:
                logger.warning("[LLM] text provider failed provider=%s error=%s", provider, str(exc))
                errors.append(f"{provider}: {exc}")

        raise RuntimeError("All text providers failed: " + " | ".join(errors))

    async def generate_vision(
        self,
        prompt: str,
        image_b64: str,
        mime_type: str,
        providers: Iterable[str] | None = None,
        temperature: float = 0.1,
    ) -> str:
        provider_order = self._iter_providers(providers, VISION_LLM_PROVIDERS)
        errors: list[str] = []

        for provider in provider_order:
            try:
                logger.info("[LLM] vision attempt provider=%s", provider)
                if provider in ("openrouter", "oxlo"):
                    return await self._generate_http_vision(provider, prompt, image_b64, mime_type, temperature)
                errors.append(f"{provider}: unsupported vision provider")
            except Exception as exc:
                logger.warning("[LLM] vision provider failed provider=%s error=%s", provider, str(exc))
                errors.append(f"{provider}: {exc}")

        raise RuntimeError("All vision providers failed: " + " | ".join(errors))


llm_gateway = LLMGateway()
