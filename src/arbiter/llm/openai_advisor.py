"""Lightweight OpenAI trade hypothesis advisor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from arbiter.config.settings import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_TIMEOUT_SECONDS,
)


SYSTEM_PROMPT = """You are a trading hypothesis reviewer for a Public Brokerage competition demo.
Review the user's proposed trade and respond with:
1. Verdict: support, lean-support, neutral, lean-reject, or reject
2. A concise thesis summary
3. The strongest supporting factors
4. The biggest risks or invalidation triggers
5. A suggested risk plan
Keep it practical, skeptical, and under 250 words.
This is analysis only, not financial advice."""


@dataclass
class TradeHypothesisRequest:
    symbol: str
    side: str
    thesis: str
    price_context: str = ""
    risk_notes: str = ""
    position_size: str = ""


class OpenAITradeAdvisor:
    """Minimal OpenAI Responses API wrapper for trade hypothesis reviews."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = OPENAI_TIMEOUT_SECONDS,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key or OPENAI_API_KEY
        self.base_url = (base_url or OPENAI_BASE_URL).rstrip("/")
        self.model = model or OPENAI_MODEL
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        if self.api_key:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def review(self, hypothesis: TradeHypothesisRequest) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        request_input = self._build_input(hypothesis)
        print("\n[OpenAI] Sending trade review request...", flush=True)
        print(f"[OpenAI] Model: {self.model}", flush=True)
        print(f"[OpenAI] Endpoint: {self.base_url}/responses", flush=True)
        print("[OpenAI] Input:", flush=True)
        print(request_input, flush=True)
        print("[OpenAI] Waiting for response...\n", flush=True)

        response = self.session.post(
            f"{self.base_url}/responses",
            json={
                "model": self.model,
                "instructions": SYSTEM_PROMPT,
                "input": request_input,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        text = self._extract_text(data)
        if not text:
            raise RuntimeError("OpenAI response did not include output text")
        return text.strip()

    @staticmethod
    def _build_input(hypothesis: TradeHypothesisRequest) -> str:
        return (
            f"Symbol: {hypothesis.symbol}\n"
            f"Side: {hypothesis.side}\n"
            f"Thesis: {hypothesis.thesis}\n"
            f"Price context: {hypothesis.price_context or 'Not provided'}\n"
            f"Position size: {hypothesis.position_size or 'Not provided'}\n"
            f"Risk notes: {hypothesis.risk_notes or 'Not provided'}"
        )

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        parts: list[str] = []
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(str(content["text"]))
        return "\n".join(parts).strip()
