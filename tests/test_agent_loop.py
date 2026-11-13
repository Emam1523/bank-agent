"""Agent loop tests with a scripted fake model (no Ollama/PostgreSQL needed).

Written before the model-driven loop was implemented (test-first).
"""

from unittest.mock import MagicMock

import pytest

from agent.cache import InMemoryCache
from agent.llm import LLMConnectionError, LLMResult, OllamaClient
from agent.wrapper import BankQueryAgent

SQL = "SELECT COUNT(*) AS n FROM bank_information;"


def reply(content="", calls=None, p=100, c=10):
    """One fake model reply. `calls` is a list of (tool_name, arguments)."""
    tool_calls = [{"name": n, "arguments": a} for n, a in (calls or [])]
    return LLMResult(content=content, tool_calls=tool_calls, prompt_tokens=p, completion_tokens=c)


def ok_rows(rows, sql=SQL):
    cols = list(rows[0]) if rows else []
    return {"status": "success", "error_type": None, "row_count": len(rows), "columns": cols,
            "rows": rows, "sql": sql, "error": None, "elapsed_ms": 1.0}


@pytest.fixture
def agent():
    llm = MagicMock(spec=OllamaClient)
    llm.base_url, llm.model = "http://localhost:11434", "qwen2.5:7b"
    llm.generate.return_value = LLMResult(content=SQL, tool_calls=[], prompt_tokens=400, completion_tokens=20)
    a = BankQueryAgent(llm_client=llm, cache=InMemoryCache(60), max_steps=6, token_budget=5000)
    a.sql_executor.execute_query = MagicMock(return_value=ok_rows([{"n": 350}]))
    return a


def script(agent, *replies):
    agent.llm.chat.side_effect = list(replies)


def test_model_calls_both_tools_and_answers_from_results(agent):
    script(agent,
           reply(calls=[("sql_generator", {"question": "How many branches?"})]),
           reply(calls=[("sql_executor", {"sql": SQL})]),
           reply("There are 350 bank branches."))
    res = agent.run("How many bank branches are there?")
    assert res["status"] == "ok" and res["error"] is None
    assert res["response"] == "There are 350 bank branches."
    assert [s["tool"] for s in res["steps"]] == ["sql_generator", "sql_executor"]
    assert res["llm_calls"] == 4  # 3 agent steps + 1 call inside sql_generator
    assert res["tokens"]["total"] == 3 * 110 + 420


def test_tool_results_are_sent_back_to_the_model(agent):
    script(agent,
           reply(calls=[("sql_executor", {"sql": SQL})]),
           reply("350 branches."))
    agent.run("How many bank branches are there?")
    history = agent.llm.chat.call_args_list[1].args[0]
    tool_msg = history[-1]
    assert tool_msg["role"] == "tool" and '"n": 350' in tool_msg["content"]


def test_sql_error_text_is_returned_to_the_model_for_a_retry(agent):
    agent.sql_executor.execute_query.side_effect = [
        {**ok_rows([]), "status": "error", "error_type": "database",
         "error": 'PostgreSQL Execution Error: column "branch" does not exist'},
        ok_rows([{"n": 350}]),
    ]
    script(agent,
           reply(calls=[("sql_executor", {"sql": "SELECT branch FROM bank_information"})]),
           reply(calls=[("sql_executor", {"sql": SQL})]),
           reply("There are 350 branches."))
    res = agent.run("How many bank branches are there?")
    second_history = agent.llm.chat.call_args_list[1].args[0]
    assert 'column \\"branch\\" does not exist' in second_history[-1]["content"]
    assert res["status"] == "ok"


def test_step_cap_stops_a_looping_model(agent):
    agent.llm.chat.return_value = reply(calls=[("sql_executor", {"sql": SQL})])
    res = agent.run("How many bank branches are there?")
    assert res["status"] == "step_cap"
    assert agent.llm.chat.call_count == 6


def test_token_budget_stops_the_run(agent):
    agent.llm.chat.return_value = reply(calls=[("sql_executor", {"sql": SQL})], p=2400, c=100)
    res = agent.run("How many bank branches are there?")
    assert res["status"] == "budget"
    assert agent.llm.chat.call_count == 2  # 2500 + 2500 reaches the 5000 budget


def test_unknown_tool_is_reported_to_the_model(agent):
    script(agent, reply(calls=[("delete_everything", {})]), reply("I cannot do that."))
    res = agent.run("How many bank branches are there?")
    history = agent.llm.chat.call_args_list[1].args[0]
    assert "Unknown tool" in history[-1]["content"]
    assert res["status"] == "ok"


def test_calculator_tool_in_the_loop(agent):
    script(agent,
           reply(calls=[("calculator", {"expression": "(500 - 400) / 400 * 100"})]),
           reply("Growth was 25%."))
    res = agent.run("Growth from 400 to 500 in percent?")
    assert res["steps"][0]["output"]["result"] == 25.0
    assert res["status"] == "ok"


def test_ungrounded_number_triggers_one_correction(agent):
    script(agent,
           reply(calls=[("sql_executor", {"sql": SQL})]),
           reply("There are 999 branches."),          # not what the tool returned
           reply("There are 350 branches."))
    res = agent.run("How many bank branches are there?")
    correction = agent.llm.chat.call_args_list[2].args[0][-1]
    assert correction["role"] == "user" and "999" in correction["content"]
    assert res["status"] == "ok" and "350" in res["response"]


def test_still_ungrounded_after_correction(agent):
    script(agent,
           reply(calls=[("sql_executor", {"sql": SQL})]),
           reply("There are 999 branches."),
           reply("There are 999 branches."))
    res = agent.run("How many bank branches are there?")
    assert res["status"] == "ungrounded"


def test_answer_without_numbers_needs_no_tools(agent):
    script(agent, reply("The database has no information about interest rates."))
    res = agent.run("What is the interest rate of Sonali Bank?")
    assert res["status"] == "ok" and res["steps"] == []


def test_llm_connection_failure(agent):
    agent.llm.chat.side_effect = LLMConnectionError("Connection refused")
    res = agent.run("How many bank branches are there?")
    assert res["status"] == "error"
    assert "cannot connect to the local LLM runtime" in res["response"]


@pytest.mark.parametrize("text,needle", [("Hello!", "Hello!"), ("Delete all banks", "only read")])
def test_small_talk_and_write_requests_skip_the_model(agent, text, needle):
    res = agent.run(text)
    assert needle.lower() in res["response"].lower() and res["status"] == "ok"
    agent.llm.chat.assert_not_called()


def test_empty_and_too_long_input(agent):
    assert agent.run("  ")["status"] == "invalid_input"
    assert agent.run("x" * 501)["status"] == "invalid_input"


def test_cache_hit_skips_the_model(agent):
    script(agent, reply(calls=[("sql_executor", {"sql": SQL})]), reply("There are 350 branches."))
    agent.run("How many bank branches are there?")
    res = agent.run("how many bank branches are there")
    assert res["source"] == "cache" and agent.llm.chat.call_count == 2


def test_failed_runs_are_not_cached(agent):
    agent.llm.chat.return_value = reply(calls=[("sql_executor", {"sql": SQL})])
    agent.run("How many bank branches are there?")
    assert agent.cache.stats()["total_keys"] == 0
