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
    reasoning_effort: str


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
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ProviderConfigurationError("OPENAI_API_KEY is required")

    reasoning_effort = (
        os.environ.get("OPENAI_REASONING_EFFORT", "low").strip().lower()
    )
    allowed_efforts = {"none", "low", "medium", "high", "xhigh", "max"}
    if reasoning_effort not in allowed_efforts:
        raise ProviderConfigurationError(
            "OPENAI_REASONING_EFFORT must be none, low, medium, high, xhigh, or max"
        )

    return ProviderConfig(
        provider="openai",
        api_key=api_key,
        model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5.6-terra").strip()
        or "gpt-5.6-terra",
        base_url=os.environ.get(
            "OPENAI_API_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/"),
        timeout_seconds=float(os.environ.get("CHAT_REQUEST_TIMEOUT_SECONDS", "90")),
        max_output_tokens=int(os.environ.get("CHAT_MAX_OUTPUT_TOKENS", "1200")),
        reasoning_effort=reasoning_effort,
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
    if event_type in {"error", "response.failed", "response.incomplete"}:
        return [("provider_error", "provider_error")]
    return []


def build_openai_request(
    system_prompt: str,
    messages: list[dict[str, str]],
    config: ProviderConfig,
) -> tuple[str, dict[str, str], dict[str, object]]:
    return (
        f"{config.base_url}/responses",
        {"Authorization": f"Bearer {config.api_key}"},
        {
            "model": config.model,
            "instructions": system_prompt,
            "input": messages,
            "stream": True,
            "max_output_tokens": config.max_output_tokens,
            "reasoning": {"effort": config.reasoning_effort},
        },
    )


async def stream_provider(
    system_prompt: str,
    messages: list[dict[str, str]],
    config: ProviderConfig | None = None,
) -> AsyncIterator[tuple[str, object]]:
    config = config or get_provider_config()
    timeout = httpx.Timeout(config.timeout_seconds, connect=10)

    url, headers, body = build_openai_request(system_prompt, messages, config)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=body
            ) as response:
                if response.status_code >= 400:
                    raise ProviderRequestError(f"provider_http_{response.status_code}")
                async for line in response.aiter_lines():
                    for event in parse_openai_responses_event(line):
                        if event[0] == "provider_error":
                            raise ProviderRequestError("provider_stream_error")
                        yield event
    except httpx.TimeoutException as exc:
        raise ProviderRequestError("provider_timeout") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestError("provider_unavailable") from exc
