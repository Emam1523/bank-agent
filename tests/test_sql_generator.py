"""SQL Generator tool tests (fake model, no Ollama needed)."""

import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from agent.llm import LLMResult, OllamaClient
from tools.sql_generator import SQLGeneratorTool


def tool_returning(text):
    llm = MagicMock(spec=OllamaClient)
    llm.generate.return_value = LLMResult(content=text, tool_calls=[], prompt_tokens=400, completion_tokens=20)
    return SQLGeneratorTool(llm_client=llm), llm


@pytest.mark.parametrize("raw,clean", [
    ("```sql\nSELECT * FROM bank_information WHERE district = 'Dhaka';\n```",
     "SELECT * FROM bank_information WHERE district = 'Dhaka';"),
    ("Here is the query:\nSELECT bank_name FROM bank_information;", "SELECT bank_name FROM bank_information;"),
    ("SELECT 1; DROP TABLE bank_information;", "SELECT 1;"),
    ("", ""),
])
def test_output_parser(raw, clean):
    assert SQLGeneratorTool.clean_sql_output(raw) == clean


def test_empty_question_is_rejected_without_a_model_call():
    tool, llm = tool_returning("SELECT 1")
    res = tool.generate_sql("   ")
    assert res["status"] == "error" and "empty" in res["error"].lower()
    llm.generate.assert_not_called()


def test_non_select_is_rejected():
    tool, _ = tool_returning("DROP TABLE bank_information;")
    res = tool.generate_sql("Delete all banks")
    assert res["status"] == "error" and "must be a SELECT query" in res["error"]


def test_success_returns_sql_and_token_counts():
    tool, _ = tool_returning("SELECT bank_name FROM bank_information WHERE district ILIKE 'khulna' LIMIT 50")
    res = tool.generate_sql("Show banks in Khulna")
    assert res["status"] == "success" and res["sql"].endswith("LIMIT 50;")
    assert res["tokens"] == {"prompt": 400, "completion": 20}


def test_out_of_scope_question():
    tool, _ = tool_returning("NO_SQL")
    res = tool.generate_sql("What is the weather?")
    assert res["status"] == "no_sql" and res["sql"] is None


def test_feedback_from_a_failed_attempt_is_in_the_prompt():
    tool, llm = tool_returning("SELECT bank_name FROM bank_information;")
    tool.generate_sql("banks", feedback='SELECT branch FROM bank_information -> column "branch" does not exist')
    prompt = llm.generate.call_args.kwargs["prompt"]
    assert "SELECT branch FROM bank_information" in prompt and "does not exist" in prompt


@pytest.mark.parametrize("module", ["tools.sql_generator", "tools.sql_executor", "tools.calculator",
                                    "agent.wrapper", "main", "evaluation.run_eval"])
def test_each_module_imports_on_its_own(module):
    """Regression: importing a tool first used to fail with a circular import."""
    proc = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
