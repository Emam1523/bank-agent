"""End-to-end tests against the real Ollama model and PostgreSQL (skipped if either is down)."""

import pytest

from agent.wrapper import BankQueryAgent
from database.connection import check_db_health

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_agent():
    agent = BankQueryAgent(use_cache=False)
    if not check_db_health():
        pytest.skip("PostgreSQL is not reachable.")
    if not agent.llm.is_available():
        pytest.skip(f"Ollama is not reachable at {agent.llm.base_url}.")
    return agent


def tools_used(result):
    return [s["tool"] for s in result["steps"]]


def test_live_model_calls_generator_then_executor(live_agent):
    result = live_agent.run("How many bank branches have INACTIVE status?")
    assert result["status"] == "ok", result
    used = tools_used(result)
    assert "sql_generator" in used and "sql_executor" in used
    assert "35" in result["response"]


def test_live_routing_number_lookup(live_agent):
    result = live_agent.run("Which bank has routing number 200260123?")
    assert result["status"] == "ok", result
    assert "Sonali" in result["response"]


def test_live_unanswerable_question_is_not_invented(live_agent):
    result = live_agent.run("What is the interest rate on Sonali Bank savings accounts?")
    assert result["status"] == "ok"
    assert "%" not in result["response"]


def test_live_greeting_uses_no_tools(live_agent):
    result = live_agent.run("Hello! What can you help me with?")
    assert result["status"] == "ok" and result["steps"] == []
