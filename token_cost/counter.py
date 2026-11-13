"""Reusable token counter: Ollama's own counts, notional cost, overhead and cache checks.

Input tokens  = Ollama `prompt_eval_count` (includes chat template + system prompt)
Output tokens = Ollama `eval_count`
Net input     = input tokens - template/system overhead (measured once with a 1-token prompt)
"""

import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Protocol

import requests

PRICE_INPUT_PER_M = 0.15   # notional USD per 1M input tokens (course price)
PRICE_OUTPUT_PER_M = 0.60  # notional USD per 1M output tokens


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Notional cost of one call."""
    return input_tokens * PRICE_INPUT_PER_M / 1e6 + output_tokens * PRICE_OUTPUT_PER_M / 1e6


class Backend(Protocol):
    def generate(self, system: str, prompt: str, options: Dict[str, Any]) -> Dict[str, Any]: ...


class OllamaBackend:
    """Calls Ollama /api/generate (non-streaming) and returns its JSON."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, timeout: int = 300):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def generate(self, system: str, prompt: str, options: Dict[str, Any]) -> Dict[str, Any]:
        res = self.session.post(f"{self.base_url}/api/generate", timeout=self.timeout, json={
            "model": self.model, "system": system, "prompt": prompt, "stream": False,
            "keep_alive": "30m", "options": options})
        res.raise_for_status()
        return res.json()


@dataclass
class CallRecord:
    prompt: str
    output: str
    input_tokens: int
    output_tokens: int
    net_input_tokens: int
    cost_usd: float
    latency_s: float
    truncated: bool  # True when generation stopped at max tokens (done_reason == "length")


class TokenCounter:
    """Sends prompts with fixed settings and records Ollama's token counts."""

    def __init__(self, backend: Backend, system: str, options: Dict[str, Any]):
        self.backend = backend
        self.system = system
        self.options = options
        self.overhead = 0  # template + system prompt tokens, set by measure_overhead()

    def _raw(self, prompt: str) -> Dict[str, Any]:
        return self.backend.generate(self.system, prompt, self.options)

    def count(self, prompt: str) -> CallRecord:
        start = time.perf_counter()
        data = self._raw(prompt)
        latency = time.perf_counter() - start
        n_in, n_out = int(data.get("prompt_eval_count", 0)), int(data.get("eval_count", 0))
        return CallRecord(prompt=prompt, output=data.get("response", "").strip(), input_tokens=n_in,
                          output_tokens=n_out, net_input_tokens=n_in - self.overhead,
                          cost_usd=cost_usd(n_in, n_out), latency_s=round(latency, 3),
                          truncated=data.get("done_reason") == "length")

    def measure_overhead(self, one_token_prompt: str = "a") -> int:
        """Template + system-prompt tokens = count('a') - 1 ('a' is a single token)."""
        self.overhead = int(self._raw(one_token_prompt).get("prompt_eval_count", 0)) - 1
        return self.overhead

    def check_cache(self, prompt: str) -> Dict[str, Any]:
        """Send the same prompt twice. If Ollama reused its cache, the 2nd count is smaller."""
        first = int(self._raw(prompt).get("prompt_eval_count", 0))
        second = int(self._raw(prompt).get("prompt_eval_count", 0))
        return {"prompt": prompt, "first": first, "second": second, "cached": second < first}


def record_dict(rec: CallRecord) -> Dict[str, Any]:
    return asdict(rec)
