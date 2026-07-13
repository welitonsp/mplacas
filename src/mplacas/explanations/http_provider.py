from __future__ import annotations

from typing import Any

import httpx

from mplacas.explanations.models import (
    ExplanationRequest,
    ExplanationSource,
    GroundedExplanation,
)


class ExplanationProviderError(RuntimeError):
    """The configured explanation service could not return a valid grounded response."""


class StructuredHttpExplanationProvider:
    """Call a configurable AI gateway using a small, evidence-only JSON contract.

    The gateway receives no raw bill, credentials, coordinates or provider payloads.
    It must return JSON with ``summary``, ``what_it_means`` and ``next_steps``.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        timeout_seconds: float = 15.0,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not endpoint_url.strip():
            raise ValueError("explanation endpoint URL cannot be blank")
        if timeout_seconds <= 0:
            raise ValueError("explanation timeout must be positive")
        self._endpoint_url = endpoint_url.strip()
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._model = model.strip() if model and model.strip() else None
        self._client = client

    async def explain(self, request: ExplanationRequest) -> GroundedExplanation:
        request.validate()
        payload: dict[str, Any] = {
            "instruction": (
                "Explain only the supplied deterministic evidence. Do not recalculate values, "
                "change severity, infer an unproven cause or add facts. Return JSON only."
            ),
            "subject": request.subject,
            "status": request.status,
            "headline": request.headline,
            "evidence": [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "message": item.message,
                    "recommended_action": item.recommended_action,
                }
                for item in request.evidence
            ],
            "response_schema": {
                "summary": "string",
                "what_it_means": "string",
                "next_steps": ["string"],
            },
        }
        if self._model is not None:
            payload["model"] = self._model

        headers = {"Content-Type": "application/json"}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            if self._client is not None:
                response = await self._client.post(
                    self._endpoint_url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(self._endpoint_url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExplanationProviderError("explanation provider request failed") from exc

        if not isinstance(body, dict):
            raise ExplanationProviderError("explanation provider returned an invalid payload")
        summary = body.get("summary")
        what_it_means = body.get("what_it_means")
        next_steps = body.get("next_steps")
        if not isinstance(summary, str) or not isinstance(what_it_means, str):
            raise ExplanationProviderError("explanation provider omitted required text fields")
        if not isinstance(next_steps, list) or not all(isinstance(item, str) for item in next_steps):
            raise ExplanationProviderError("explanation provider returned invalid next steps")

        result = GroundedExplanation(
            source=ExplanationSource.AI_ASSISTED,
            summary=summary.strip(),
            what_it_means=what_it_means.strip(),
            next_steps=tuple(item.strip() for item in next_steps if item.strip())[:5],
            disclaimer="Provider output; application disclaimer will be enforced by the service.",
        )
        result.validate()
        return result
