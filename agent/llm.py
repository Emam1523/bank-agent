"""Client for the single local Ollama LLM (default: qwen2.5:7b).

Two endpoints are used:
- /api/chat     : the agent loop, with a list of tools the model may call;
- /api/generate : the SQL Generator tool's own focused call.
Every call returns its token counts so the agent can enforce a token budget.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# Shared by both endpoints. Keeping num_ctx identical matters: a different
# num_ctx makes Ollama reload the model.
BASE_OPTIONS: Dict[str, Any] = {
    "temperature": 0.0,     # greedy decoding: same input -> same output
    "top_p": 0.9,           # nucleus cut-off (only matters if temperature > 0)
    "top_k": 20,            # candidate cut-off (only matters if temperature > 0)
    "seed": 42,             # reproducible runs
    "num_ctx": 4096,        # agent history + tool results fit; small window = less RAM
    "repeat_penalty": 1.0,  # off: SQL and tool calls legitimately repeat names
}
SQL_OPTIONS = {**BASE_OPTIONS, "num_predict": 200, "stop": [";", "\nQ:"]}  # one short statement
CHAT_OPTIONS = {**BASE_OPTIONS, "num_predict": 300}                        # tool call or short answer


class LLMConnectionError(Exception):
    """Raised when Ollama is unreachable or returns an error."""


@dataclass
class LLMResult:
    """One model call: text, requested tool calls and Ollama's token counts."""
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # [{"name", "arguments"}]
    prompt_tokens: int = 0
    completion_tokens: int = 0


def parse_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise Ollama tool calls to [{"name", "arguments"}].

    Fallback: some small models write the call as JSON text in `content`
    ({"name": ..., "arguments": {...}}); that is accepted too.
    """
    calls = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"_raw": args}
        calls.append({"name": fn.get("name", ""), "arguments": args})
    if not calls:
        text = (message.get("content") or "").strip().strip("`").removeprefix("json").strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
                name = data.get("name") or data.get("tool")
                if name:
                    calls.append({"name": name, "arguments": data.get("arguments") or data.get("args") or {}})
            except (json.JSONDecodeError, AttributeError):
                pass
    return calls


class OllamaClient:
    """Minimal HTTP client for Ollama."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None,
                 timeout_seconds: int = 180):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
        self.keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "30m")  # keep model loaded between questions
        self.timeout = timeout_seconds
        self.session = requests.Session()  # reuses the TCP connection

    def is_available(self) -> bool:
        """True if the Ollama server answers."""
        try:
            return self.session.get(f"{self.base_url}/api/tags", timeout=3).status_code == 200
        except requests.RequestException:
            return False

    def warm_up(self) -> None:
        """Load the model into memory so the first question is not slow (best effort)."""
        try:
            self._post("/api/generate", {"prompt": "Hi", "options": {**BASE_OPTIONS, "num_predict": 1}})
        except LLMConnectionError:
            pass

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = {"model": self.model, "stream": False, "keep_alive": self.keep_alive, **payload}
        try:
            res = self.session.post(f"{self.base_url}{path}", json=body, timeout=self.timeout)
        except requests.RequestException as err:
            raise LLMConnectionError(f"Cannot reach Ollama at {self.base_url}: {err}") from err
        if res.status_code != 200:
            raise LLMConnectionError(f"Ollama returned HTTP {res.status_code}: {res.text[:200]}")
        return res.json()

    def generate(self, prompt: str, system: str) -> LLMResult:
        """Single completion (used by the SQL Generator tool)."""
        data = self._post("/api/generate", {"system": system, "prompt": prompt, "options": SQL_OPTIONS})
        return LLMResult(content=data.get("response", "").strip(),
                         prompt_tokens=data.get("prompt_eval_count", 0),
                         completion_tokens=data.get("eval_count", 0))

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMResult:
        """One agent step: the model either answers or asks for tool calls."""
        data = self._post("/api/chat", {"messages": messages, "tools": tools, "options": CHAT_OPTIONS})
        message = data.get("message", {})
        calls = parse_tool_calls(message)
        return LLMResult(content="" if calls and not message.get("tool_calls") else (message.get("content") or "").strip(),
                         tool_calls=calls,
                         prompt_tokens=data.get("prompt_eval_count", 0),
                         completion_tokens=data.get("eval_count", 0))
