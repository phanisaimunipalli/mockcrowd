"""Any OpenAI-compatible chat endpoint: hosted APIs, OpenRouter, Ollama, LM Studio, vLLM."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..util import urlopen
from .base import SYSTEM_PROMPT, Brain, BrainError

OLLAMA_BASE = "http://localhost:11434/v1"


class OpenAICompatible(Brain):
    name = "openai"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 600.0,
    ):
        super().__init__(model=model or os.environ.get("MOCKCROWD_MODEL"), timeout=timeout)
        self.base_url = (base_url or os.environ.get("MOCKCROWD_API_BASE") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("MOCKCROWD_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.base_url:
            raise BrainError("set MOCKCROWD_API_BASE (for example https://api.openai.com/v1)")
        if not self.model:
            raise BrainError("set a model with --model or MOCKCROWD_MODEL")

    def complete(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.9,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise BrainError(f"HTTP {exc.code}: {exc.read().decode()[:300]}") from exc
        except urllib.error.URLError as exc:
            raise BrainError(f"cannot reach {self.base_url}: {exc.reason}") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise BrainError(f"unexpected response: {str(data)[:300]}") from exc


class Ollama(OpenAICompatible):
    name = "ollama"

    def __init__(self, model: str | None = None, timeout: float = 1200.0):
        super().__init__(
            model=model or os.environ.get("MOCKCROWD_MODEL"),
            base_url=os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE),
            api_key="ollama",
            timeout=timeout,
        )


def ollama_running() -> bool:
    base = os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE).removesuffix("/v1")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2):
            return True
    except Exception:
        return False
