from __future__ import annotations

import json

import httpx
import pytest

from mplacas.explanations.http_provider import (
    ExplanationProviderError,
    StructuredHttpExplanationProvider,
)
from mplacas.explanations.models import DiagnosticEvidence, ExplanationRequest, ExplanationSource


def _request() -> ExplanationRequest:
    return ExplanationRequest(
        subject="Synthetic plant",
        status="ATTENTION",
        headline="The cycle requires monitoring.",
        evidence=(
            DiagnosticEvidence(
                code="LOW_SELF_CONSUMPTION",
                severity="WARNING",
                message="Self-consumption is below the configured threshold.",
                recommended_action="Review daytime load distribution.",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_structured_provider_sends_only_normalized_evidence() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "summary": "The cycle deserves attention.",
                "what_it_means": "The supplied evidence indicates low self-consumption.",
                "next_steps": ["Review daytime load distribution."],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = StructuredHttpExplanationProvider(
            endpoint_url="https://example.invalid/explain",
            api_key="synthetic-secret",
            model="synthetic-model",
            client=client,
        )
        result = await provider.explain(_request())

    assert result.source is ExplanationSource.AI_ASSISTED
    assert captured["authorization"] == "Bearer synthetic-secret"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "synthetic-model"
    assert payload["evidence"][0]["code"] == "LOW_SELF_CONSUMPTION"
    serialized = json.dumps(payload)
    assert "synthetic-secret" not in serialized
    assert "cpf" not in serialized.lower()


@pytest.mark.asyncio
async def test_structured_provider_rejects_invalid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"summary": "Incomplete"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = StructuredHttpExplanationProvider(
            endpoint_url="https://example.invalid/explain",
            client=client,
        )
        with pytest.raises(ExplanationProviderError, match="required text fields"):
            await provider.explain(_request())
