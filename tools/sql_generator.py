"""Tool 1 - SQL Generator: one data question -> one PostgreSQL SELECT (never executes).

Design choice (assignment requirement 2): this tool makes its OWN model call
with a focused prompt that contains the schema. The agent's prompt therefore
stays small, the SQL prompt can hold schema details and examples, and the tool
can be tested on its own. Cost: one extra model call per query.
"""

import re
from typing import Any, Dict, Optional

from agent.llm import OllamaClient
from agent.prompts import NO_SQL, RETRY_TEMPLATE, SQL_SYSTEM_PROMPT


class SQLGeneratorTool:
    """Asks the LLM for SQL and parses its raw text into a clean statement."""

    name = "sql_generator"

    def __init__(self, llm_client: Optional[OllamaClient] = None):
        self.llm = llm_client or OllamaClient()

    @staticmethod
    def clean_sql_output(raw_output: str) -> str:
        """Output parser: strip markdown fences and prose, keep one statement ending in ';'."""
        if not raw_output:
            return ""
        text = re.sub(r"```(?:sql)?", "", raw_output, flags=re.IGNORECASE).strip()
        start = re.search(r"\b(SELECT|WITH)\b", text, re.IGNORECASE)
        if start:
            text = text[start.start():]
        text = text.split(";")[0].strip()
        return f"{text};" if text else ""

    def generate_sql(self, question: str, feedback: Optional[str] = None) -> Dict[str, Any]:
        """Generate SQL for `question`. `feedback` = the previous SQL and its error, for a fix.

        Returns {"status": "success"|"no_sql"|"error", "sql", "error", "question", "tokens"}.
        Raises LLMConnectionError (the agent turns it into its fallback message).
        """
        base = {"sql": None, "error": None, "question": question, "tokens": {"prompt": 0, "completion": 0}}
        if not question or not question.strip():
            return {**base, "status": "error", "error": "Cannot generate SQL for an empty question."}

        q = question.strip()
        prompt = RETRY_TEMPLATE.format(question=q, feedback=feedback) if feedback else f"Q: {q}"
        result = self.llm.generate(prompt=prompt, system=SQL_SYSTEM_PROMPT)
        base["tokens"] = {"prompt": result.prompt_tokens, "completion": result.completion_tokens}

        if NO_SQL in result.content.upper():
            return {**base, "status": "no_sql",
                    "error": "The database has no data that answers this question."}
        sql = self.clean_sql_output(result.content)
        if not sql:
            return {**base, "status": "error", "error": "The model produced no SQL."}
        first_word = sql.split()[0].upper()
        if first_word not in ("SELECT", "WITH"):
            return {**base, "status": "error", "sql": sql,
                    "error": f"Generated statement must be a SELECT query, got '{first_word}'."}
        return {**base, "status": "success", "sql": sql}
