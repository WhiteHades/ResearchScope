from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_output_tokens: int


def chat_enabled() -> bool:
    return os.environ.get("CHAT_ENABLED", "false").strip().lower() == "true"


def provider_configured() -> bool:
    if not chat_enabled():
        return False
    try:
        get_provider_config()
        return True
    except ProviderConfigurationError:
        return False


def get_provider_config() -> ProviderConfig:
    provider = os.environ.get("CHAT_PROVIDER", "").strip().lower()
    settings = {
        "groq": (
            "GROQ_API_KEY",
            "GROQ_CHAT_MODEL",
            "GROQ_API_BASE_URL",
            "https://api.groq.com/openai/v1",
        ),
        "openai": (
            "OPENAI_API_KEY",
            "OPENAI_CHAT_MODEL",
            "OPENAI_API_BASE_URL",
            "https://api.openai.com/v1",
        ),
        "anthropic": (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_CHAT_MODEL",
            "ANTHROPIC_API_BASE_URL",
            "https://api.anthropic.com/v1",
        ),
    }
    if provider not in settings:
        raise ProviderConfigurationError(
            "CHAT_PROVIDER must be groq, openai, or anthropic"
        )
    key_name, model_name, base_name, default_base = settings[provider]
    api_key = os.environ.get(key_name, "").strip()
    model = os.environ.get(model_name, "").strip()
    if not api_key or not model:
        raise ProviderConfigurationError(f"{key_name} and {model_name} are required")
    return ProviderConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=os.environ.get(base_name, default_base).rstrip("/"),
        timeout_seconds=float(os.environ.get("CHAT_REQUEST_TIMEOUT_SECONDS", "90")),
        max_output_tokens=int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "1200")),
    )


def _json_data(line: str) -> dict | None:
    if not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_openai_compatible_event(line: str) -> list[tuple[str, object]]:
    data = _json_data(line)
    if not data:
        return []
    events: list[tuple[str, object]] = []
    choices = data.get("choices") or []
    if choices:
        text = (choices[0].get("delta") or {}).get("content") or ""
        if text:
            events.append(("delta", text))
    usage = data.get("usage")
    if usage:
        events.append(
            (
                "usage",
                {
                    "input_tokens": int(usage.get("prompt_tokens") or 0),
                    "output_tokens": int(usage.get("completion_tokens") or 0),
                },
            )
        )
    return events


def parse_openai_responses_event(line: str) -> list[tuple[str, object]]:
    data = _json_data(line)
    if not data:
        return []
    event_type = data.get("type") or ""
    if event_type == "response.output_text.delta" and data.get("delta"):
        return [("delta", data["delta"])]
    if event_type == "response.completed":
        usage = (data.get("response") or {}).get("usage") or {}
        return [
            (
                "usage",
                {
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                },
            )
        ]
    if event_type == "error":
        return [("provider_error", "provider_error")]
    return []


def parse_anthropic_event(line: str) -> list[tuple[str, object]]:
    data = _json_data(line)
    if not data:
        return []
    event_type = data.get("type") or ""
    if event_type == "content_block_delta":
        text = (data.get("delta") or {}).get("text") or ""
        return [("delta", text)] if text else []
    if event_type == "message_start":
        usage = (data.get("message") or {}).get("usage") or {}
        return [("usage", {"input_tokens": int(usage.get("input_tokens") or 0)})]
    if event_type == "message_delta":
        usage = data.get("usage") or {}
        return [("usage", {"output_tokens": int(usage.get("output_tokens") or 0)})]
    if event_type == "error":
        return [("provider_error", "provider_error")]
    return []


async def stream_provider(
    system_prompt: str,
    messages: list[dict[str, str]],
    config: ProviderConfig | None = None,
) -> AsyncIterator[tuple[str, object]]:
    config = config or get_provider_config()
    timeout = httpx.Timeout(config.timeout_seconds, connect=10)

    if config.provider == "groq":
        url = f"{config.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}"}
        body = {
            "model": config.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": config.max_output_tokens,
        }
        parser = parse_openai_compatible_event
    elif config.provider == "openai":
        url = f"{config.base_url}/responses"
        headers = {"Authorization": f"Bearer {config.api_key}"}
        body = {
            "model": config.model,
            "instructions": system_prompt,
            "input": messages,
            "stream": True,
            "max_output_tokens": config.max_output_tokens,
        }
        parser = parse_openai_responses_event
    else:
        url = f"{config.base_url}/messages"
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": config.model,
            "system": system_prompt,
            "messages": messages,
            "stream": True,
            "max_tokens": config.max_output_tokens,
        }
        parser = parse_anthropic_event

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=body
            ) as response:
                if response.status_code >= 400:
                    raise ProviderRequestError(f"provider_http_{response.status_code}")
                async for line in response.aiter_lines():
                    for event in parser(line):
                        if event[0] == "provider_error":
                            raise ProviderRequestError("provider_stream_error")
                        yield event
    except httpx.TimeoutException as exc:
        raise ProviderRequestError("provider_timeout") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestError("provider_unavailable") from exc
