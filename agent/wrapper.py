"""Agent loop (hand-written, no agent framework).

    question -> guard -> [ model step -> tool calls -> tool results back to model ]* -> answer
                                   (step cap, token budget)                     -> grounding check

The MODEL decides which tool to call (Ollama native tool calling). The loop
stops with a clear status: ok | step_cap | budget | ungrounded | error | invalid_input.
"""

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from agent.cache import InMemoryCache
from agent.llm import LLMConnectionError, OllamaClient
from agent.prompts import AGENT_SYSTEM_PROMPT, AGENT_TOOLS
from tools.calculator import CalculatorTool
from tools.sql_executor import SQLExecutorTool
from tools.sql_generator import SQLGeneratorTool

MAX_QUERY_CHARS = 500   # protects the prompt size
MAX_STEPS = 8           # step cap: model calls per question
TOKEN_BUDGET = 20_000   # budget cap: prompt + completion tokens per question (all model calls)
ROWS_TO_MODEL = 20      # rows sent back to the model per query (keeps the context small)
DISPLAY_ROWS = 20
MAX_CELL_CHARS = 40

SMALL_TALK = re.compile(
    r"^\s*(hi|hello|hey|salam|assalamu\s*alaikum|good\s+(morning|afternoon|evening)|"
    r"thanks?|thank\s+you|who\s+are\s+you|what\s+can\s+you\s+do|help)\b", re.IGNORECASE)
DATA_HINT = re.compile(
    r"\b(banks?|branch(es)?|accounts?|routing|swift|district|balance|customers?|users?|deposits?|"
    r"withdrawals?|transactions?|show|list|find|count|how\s+many|total|average)\b", re.IGNORECASE)
WRITE_INTENT = re.compile(
    r"\b(delete|remove|drop|insert|update|modify|alter|truncate|create|transfer|deposit\s+\d|withdraw)\b",
    re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")

HELP_REPLY = ("Hello! I answer questions about Bangladeshi bank branches, customer accounts and transactions, "
              "e.g. 'How many active branches are in Dhaka?' or 'Total deposits in 2025?'.")
READ_ONLY_REPLY = "I can only read data. Creating, changing or deleting records is not allowed."


def extract_numbers(text: str) -> List[float]:
    """All numbers in a text: '1,234.5 BDT (12%)' -> [1234.5, 12.0]."""
    return [float(m.replace(",", "")) for m in NUMBER.findall(text or "")]


def _close(a: float, b: float) -> bool:
    """Equal up to rounding: 0.01 absolute or 0.5% relative."""
    return abs(a - b) <= 0.01 or abs(a - b) <= 0.005 * abs(b)


class BankQueryAgent:
    """One local LLM + 3 tools (sql_generator, sql_executor, calculator) + TTL cache memory."""

    def __init__(self, llm_client: Optional[OllamaClient] = None, cache: Optional[InMemoryCache] = None,
                 use_cache: bool = True, max_steps: int = MAX_STEPS, token_budget: int = TOKEN_BUDGET):
        self.llm = llm_client or OllamaClient()
        self.cache = cache or InMemoryCache()
        self.use_cache = use_cache
        self.max_steps = max_steps
        self.token_budget = token_budget
        self.sql_generator = SQLGeneratorTool(llm_client=self.llm)
        self.sql_executor = SQLExecutorTool()
        self.calculator = CalculatorTool()
        self.usage = {"questions": 0, "llm_calls": 0, "tokens": 0}  # session totals for `stats`

    # ------------------------------------------------------------------ guard
    @staticmethod
    def plan(query: str) -> Dict[str, Any]:
        """Cheap guard before any model call: refuse writes, answer small talk."""
        if WRITE_INTENT.search(query):
            return {"intent": "write", "reply": READ_ONLY_REPLY}
        if SMALL_TALK.match(query) and not DATA_HINT.search(query):
            return {"intent": "small_talk", "reply": HELP_REPLY}
        return {"intent": "data", "reply": None}

    # ------------------------------------------------------------------ main entry
    def run(self, user_query: str, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """Answer one question.

        Returns {"query", "response", "status", "source", "steps", "tokens", "llm_calls",
                 "elapsed_s", "error", "table"}.
        """
        emit = log_callback or (lambda _msg: None)
        start = time.perf_counter()
        query = (user_query or "").strip()
        state: Dict[str, Any] = {"query": query, "response": "", "status": "ok", "source": "agent",
                                 "steps": [], "tokens": {"prompt": 0, "completion": 0, "total": 0},
                                 "llm_calls": 0, "elapsed_s": 0.0, "error": None, "table": None}

        def finish(**updates: Any) -> Dict[str, Any]:
            state.update(updates, elapsed_s=round(time.perf_counter() - start, 2))
            return state

        if not query or len(query) > MAX_QUERY_CHARS:
            return finish(status="invalid_input",
                          response=f"Please enter a question of 1-{MAX_QUERY_CHARS} characters.")

        if self.use_cache:
            cached = self.cache.get(query)
            if cached is not None:
                emit("[Cache] HIT - returning stored answer")
                return finish(response=cached["response"], table=cached["table"], source="cache")
            emit("[Cache] MISS")

        guard = self.plan(query)
        if guard["reply"]:
            emit(f"[Guard] {guard['intent']} - answered without the model")
            return finish(response=guard["reply"])

        try:
            self._loop(query, state, emit)
        except LLMConnectionError as err:
            emit(f"[Error] {err}")
            state.update(status="error", error=str(err), response=(
                f"Sorry, I cannot connect to the local LLM runtime (Ollama). Please ensure Ollama is "
                f"running at {self.llm.base_url} with model '{self.llm.model}'."))
        except Exception as err:  # last-resort safety net: never crash the CLI
            emit(f"[Error] {err}")
            state.update(status="error", error=str(err), response=f"An unexpected error occurred: {err}")

        if state["status"] == "ok" and self.use_cache:
            self.cache.set(query, {"response": state["response"], "table": state["table"]})
        self.usage["questions"] += 1
        self.usage["llm_calls"] += state["llm_calls"]
        self.usage["tokens"] += state["tokens"]["total"]
        emit(f"[Status] {state['status']} | {state['llm_calls']} model calls | "
             f"{state['tokens']['total']} tokens")
        return finish(source="llm" if state["status"] == "ok" else "error")

    # ------------------------------------------------------------------ the loop
    def _loop(self, query: str, state: Dict[str, Any], emit: Callable[[str], None]) -> None:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": AGENT_SYSTEM_PROMPT},
                                          {"role": "user", "content": query}]
        tokens = state["tokens"]
        corrected = False

        for step in range(1, self.max_steps + 1):
            if tokens["total"] >= self.token_budget:
                state.update(status="budget", response="Stopped: the token budget for this question was used up.")
                return
            result = self.llm.chat(list(messages), AGENT_TOOLS)
            self._count(state, result.prompt_tokens, result.completion_tokens)

            if result.tool_calls:  # the model chose tool(s)
                messages.append({"role": "assistant", "content": result.content, "tool_calls": [
                    {"function": {"name": c["name"], "arguments": c["arguments"]}} for c in result.tool_calls]})
                for call in result.tool_calls:
                    emit(f"[Step {step}] model -> {call['name']}({json.dumps(call['arguments'], ensure_ascii=False)})")
                    output = self._call_tool(call["name"], call["arguments"], state)
                    self._log_tool(call["name"], output, emit)
                    messages.append({"role": "tool", "tool_name": call["name"],
                                     "content": json.dumps(self._for_model(call["name"], output), default=str)})
                continue

            answer = result.content or "I could not produce an answer."
            bad = self.ungrounded_numbers(answer, query, state["steps"])
            if bad and not corrected:  # verification: numbers must come from tools
                corrected = True
                emit(f"[Verify] numbers not returned by any tool: {bad} - asking the model to use tools")
                messages += [{"role": "assistant", "content": answer},
                             {"role": "user", "content": f"Your answer contains numbers that no tool returned: {bad}. "
                              "Get them with the tools (sql_generator, sql_executor, calculator) "
                              "or say that the database cannot answer."}]
                continue
            state.update(status="ungrounded" if bad else "ok", response=answer)
            emit("[Verify] answer is grounded in tool results" if not bad else "[Verify] still ungrounded")
            return

        state.update(status="step_cap", response="Stopped: too many steps without a final answer.")

    # ------------------------------------------------------------------ tools
    def _call_tool(self, name: str, args: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Run one tool chosen by the model and record it in the step trace."""
        try:
            if name == "sql_generator":
                output = self.sql_generator.generate_sql(str(args.get("question", "")), args.get("feedback") or None)
                used = output["tokens"]
                self._count(state, used["prompt"], used["completion"], model_call=bool(used["prompt"]))
            elif name == "sql_executor":
                output = self.sql_executor.execute_query(str(args.get("sql", "")))
                if output["status"] == "success" and output["row_count"] > 1:
                    state["table"] = self.format_table(output)
            elif name == "calculator":
                output = self.calculator.calculate(str(args.get("expression", "")))
            else:
                output = {"status": "error", "error": f"Unknown tool '{name}'. Use sql_generator, sql_executor or calculator."}
        except LLMConnectionError:
            raise
        except Exception as err:  # bad arguments from the model must not crash the loop
            output = {"status": "error", "error": f"Tool failed: {err}"}
        state["steps"].append({"tool": name, "input": args, "output": output})
        return output

    @staticmethod
    def _count(state: Dict[str, Any], prompt: int, completion: int, model_call: bool = True) -> None:
        t = state["tokens"]
        t["prompt"] += prompt
        t["completion"] += completion
        t["total"] = t["prompt"] + t["completion"]
        if model_call:
            state["llm_calls"] += 1

    @staticmethod
    def _for_model(name: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """Compact tool result for the model's context (fewer tokens)."""
        if name == "sql_executor" and output.get("status") == "success":
            rows = output["rows"]
            compact = {"status": "success", "row_count": output["row_count"], "rows": rows[:ROWS_TO_MODEL]}
            if len(rows) > ROWS_TO_MODEL:
                compact["note"] = f"only the first {ROWS_TO_MODEL} of {len(rows)} rows are shown"
            return compact
        keep = {"sql_generator": ("status", "sql", "error"), "calculator": ("status", "result", "error")}
        return {k: output.get(k) for k in keep.get(name, ("status", "error")) if output.get(k) is not None}

    @staticmethod
    def _log_tool(name: str, output: Dict[str, Any], emit: Callable[[str], None]) -> None:
        if output.get("status") not in ("success",):
            emit(f"[Tool: {name}] {output.get('status')}: {output.get('error')}")
        elif name == "sql_generator":
            emit(f"[Tool: sql_generator] SQL: {output['sql']}")
        elif name == "sql_executor":
            emit(f"[Tool: sql_executor] {output['row_count']} row(s) in {output['elapsed_ms']} ms")
        else:
            emit(f"[Tool: calculator] {output.get('expression')} = {output.get('result')}")

    # ------------------------------------------------------------------ verification + display
    @staticmethod
    def ungrounded_numbers(answer: str, question: str, steps: List[Dict[str, Any]]) -> List[float]:
        """Numbers in the answer that appear neither in the question nor in any successful tool output."""
        known = extract_numbers(question)
        for s in steps:
            if s["output"].get("status") == "success":
                known += extract_numbers(json.dumps(s["output"].get("rows", s["output"].get("result")), default=str))
                known.append(float(s["output"].get("row_count", 0) or 0))
        return [n for n in extract_numbers(answer) if not any(_close(n, k) for k in known)]

    @staticmethod
    def format_table(result: Dict[str, Any]) -> str:
        """Rows as a compact text table for the terminal (no model call)."""
        rows, cols = result["rows"], result["columns"]

        def cell(value: Any) -> str:
            if isinstance(value, float):
                value = round(value, 2)
            text = "-" if value is None else str(value)
            return text if len(text) <= MAX_CELL_CHARS else text[:MAX_CELL_CHARS - 3] + "..."

        shown = [[cell(r[c]) for c in cols] for r in rows[:DISPLAY_ROWS]]
        widths = [max(len(c), *(len(r[i]) for r in shown)) for i, c in enumerate(cols)]
        line = lambda vals: " | ".join(v.ljust(w) for v, w in zip(vals, widths)).rstrip()
        table = [line(cols), "-+-".join("-" * w for w in widths), *(line(r) for r in shown)]
        more = f" (showing first {DISPLAY_ROWS})" if len(rows) > DISPLAY_ROWS else ""
        return f"{len(rows)} row(s){more}:\n" + "\n".join(table)
