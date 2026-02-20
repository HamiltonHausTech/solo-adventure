from __future__ import annotations

import os
import random
import sys
import time
from typing import Optional

try:
    from openai import OpenAI
    from openai import RateLimitError as OpenAIRateLimitError
except Exception:  # pragma: no cover - optional dependency at runtime
    OpenAI = None
    OpenAIRateLimitError = Exception  # type: ignore

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0
RATE_LIMIT_DELAY = 60.0  # Wait 60s when rate limited (RPM resets per minute)
MAX_TOKENS = 150  # Keeps responses short; prompts ask for ~120 words / 1 sentence


def _debug(msg: str) -> None:
    if os.getenv("OPENAI_DEBUG", "").lower() in ("1", "true", "yes"):
        print(f"[OpenAI] {msg}", file=sys.stderr)


class LLMClient:
    def __init__(
        self,
        model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model_name = (model or os.getenv("OPENAI_MODEL", "")).strip()
        # gpt-4o-mini is faster than gpt-4.1-mini; use OPENAI_MODEL to override
        self.model = model_name or "gpt-4o-mini"
        self.stub = not self.api_key or OpenAI is None
        self._client = OpenAI(api_key=self.api_key) if not self.stub else None
        self.timeout = timeout
        self.max_retries = max_retries

    def gm_reply(self, system_prompt: str, user_prompt: str) -> str:
        text, _ = self.gm_reply_with_source(system_prompt, user_prompt)
        return text

    def gm_reply_with_source(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        """Return (response_text, source) where source is 'stub' or 'ai' or 'fallback'."""
        if self.stub:
            return self._stub_gm(), "stub"
        _debug("GM narration request")
        result, source = self._chat_with_fallback_typed(
            system_prompt, user_prompt, self._stub_gm
        )
        return result, source

    def companion_reply(self, system_prompt: str, user_prompt: str) -> str:
        if self.stub or os.getenv("OPENAI_SKIP_COMPANION", "").lower() in ("1", "true", "yes"):
            return self._stub_companion()
        _debug("Companion suggestion request")
        return self._chat_with_fallback(system_prompt, user_prompt, self._stub_companion)

    def _chat_with_fallback_typed(
        self, system_prompt: str, user_prompt: str, fallback
    ) -> tuple[str, str]:
        """Like _chat_with_fallback but returns (result, 'ai'|'fallback')."""
        for attempt in range(self.max_retries):
            try:
                _debug("API call starting...")
                result = self._chat(system_prompt, user_prompt)
                _debug("API call succeeded")
                return result, "ai"
            except OpenAIRateLimitError as e:
                _debug(f"429 error: {e}")
                err_body = getattr(e, "body", None) or {}
                code = (err_body.get("error") or {}).get("code", "")
                if code == "insufficient_quota" or "insufficient_quota" in str(e):
                    print(
                        "\n[OpenAI] Quota exceeded. Add payment method or credits at "
                        "https://platform.openai.com/account/billing — using fallback.",
                        file=sys.stderr,
                    )
                    res = fallback() if callable(fallback) else str(fallback)
                    return res, "fallback"
                print(
                    "\n[Rate limit] OpenAI API rate limit hit. "
                    "Using fallback. Set OPENAI_DEBUG=1 for details.",
                    file=sys.stderr,
                )
                if attempt < self.max_retries - 1:
                    delay = RATE_LIMIT_DELAY
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after is not None:
                        delay = float(retry_after)
                    print(f"[Rate limit] Waiting {delay:.0f}s before retry...", file=sys.stderr)
                    time.sleep(delay)
                else:
                    res = fallback() if callable(fallback) else str(fallback)
                    return res, "fallback"
            except Exception as e:
                _debug(f"API error: {type(e).__name__}: {e}")
                if attempt < self.max_retries - 1:
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    time.sleep(delay)
                else:
                    print(
                        f"\n[OpenAI] Request failed after {self.max_retries} retries: {e}",
                        file=sys.stderr,
                    )
                    res = fallback() if callable(fallback) else str(fallback)
                    return res, "fallback"

    def _chat_with_fallback(
        self, system_prompt: str, user_prompt: str, fallback: object
    ) -> str:
        result, _ = self._chat_with_fallback_typed(system_prompt, user_prompt, fallback)
        return result

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=MAX_TOKENS,
            timeout=self.timeout,
        )
        return response.choices[0].message.content.strip()

    def _stub_gm(self) -> str:
        lines = [
            "The ruin creaks with old stone. What do you do?",
            "You take a breath as the air shifts. What's your move?",
            "The watchtower looms, silent and watchful. What do you do next?",
        ]
        return random.choice(lines)

    def _stub_companion(self) -> str:
        lines = [
            "Mara whispers, 'Keep your distance and watch for traps.'",
            "Mara says, 'Let me cover you while you act.'",
            "Mara mutters, 'Slow and steady - no sudden moves.'",
        ]
        return random.choice(lines)
