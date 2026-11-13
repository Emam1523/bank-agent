"""Schema knowledge, the agent's system prompt and the SQL Generator's prompt.

`SCHEMA` is the single source of truth for schema awareness: it is shown to the
SQL Generator and used by the SQL Executor to allow-list tables and columns.
Keep it in sync with database/schema.sql.
"""

SCHEMA = {
    "bank_information": [
        "bank_id", "bank_name", "routing_number", "swift_code", "district", "address", "status",
    ],
    "user_accounts": [
        "account_id", "user_name", "email", "account_number", "bank_id",
        "account_type", "balance", "created_at",
    ],
    "transactions": ["txn_id", "account_id", "txn_date", "txn_type", "amount"],
}

NO_SQL = "NO_SQL"  # SQL Generator's answer when the data does not exist in the schema

# ---------------------------------------------------------------------------- agent
AGENT_SYSTEM_PROMPT = """You answer questions about a Bangladeshi bank database (branches, customer accounts, deposit/withdrawal transactions).
Every number in your answer must come from a tool result. Never guess numbers or do arithmetic yourself.

Tools:
- sql_generator(question): writes one SQL query for a data question; it knows the schema.
- sql_executor(sql): runs that SQL and returns rows or an error.
- calculator(expression): arithmetic on numbers taken from tool results (differences, percentages, ratios, growth).

Method:
1. Call sql_generator with the data question, then sql_executor with the exact SQL it returned.
2. If sql_executor returns an error, call sql_generator again with feedback = the SQL and the error.
3. For any difference, percentage, ratio or growth, call calculator with numbers from the rows.
4. If sql_generator says the database has no such data, answer that the database cannot answer the question.
5. Final answer: one or two short sentences with the numbers exactly as the tools returned them."""

AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "sql_generator",
        "description": "Write one read-only SQL query that answers a data question about branches, accounts or transactions.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "The data question in plain English."},
            "feedback": {"type": "string", "description": "Optional: the previous SQL and its error, to get a corrected query."},
        }, "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "sql_executor",
        "description": "Run a SELECT query on the bank database and return the rows, or an error message.",
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "The SQL returned by sql_generator."},
        }, "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "calculator",
        "description": "Evaluate an arithmetic expression, e.g. (520 - 400) / 400 * 100.",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "Numbers and + - * / ** ( ) round() only."},
        }, "required": ["expression"]}}},
]

# ---------------------------------------------------------------------------- SQL generator
SQL_SYSTEM_PROMPT = f"""You translate questions about Bangladeshi bank branches, customer accounts and transactions into ONE PostgreSQL query.

Schema:
bank_information(bank_id PK, bank_name e.g. 'BRAC Bank PLC', routing_number 9-digit text, swift_code, district e.g. 'Dhaka', address, status 'ACTIVE'|'INACTIVE')
user_accounts(account_id PK, user_name, email, account_number e.g. 'AC-12345678', bank_id FK -> bank_information.bank_id, account_type 'SAVINGS'|'CURRENT'|'SALARY'|'FIXED_DEPOSIT', balance NUMERIC BDT, created_at DATE)
transactions(txn_id PK, account_id FK -> user_accounts.account_id, txn_date DATE (2024-2025), txn_type 'DEPOSIT'|'WITHDRAWAL', amount NUMERIC BDT)
One bank has many branches (rows) across districts.

Rules:
- Output only the SQL ending with ; - no explanation, no markdown.
- Only SELECT (or WITH ... SELECT). Never modify data.
- Text filters are case-insensitive: district ILIKE 'dhaka', bank_name ILIKE '%brac%'.
- Select only the columns needed; use COUNT/SUM/AVG/MAX/MIN for numeric questions; ROUND(AVG(x), 2).
- Filter by bank or district with JOIN ... ON keys or IN (SELECT ...), never col = (SELECT ...). Years: EXTRACT(YEAR FROM txn_date) = 2025.
- Never type a number you were not given (a minimum, a total, a count): compute it with MIN/MAX/SUM/COUNT/AVG.
- To compare years, types or statuses, return one row with one column per group using SUM(...) FILTER (WHERE ...) or COUNT(*) FILTER (WHERE ...).
- "Ratio of A to B" = A divided by B.
- Add LIMIT 50 to list queries.
- If the question needs data that is not in this schema (interest rates, loans, phone numbers...), output exactly {NO_SQL}

Q: active banks in Sylhet
SELECT bank_name, routing_number, address FROM bank_information WHERE district ILIKE 'sylhet' AND status = 'ACTIVE' LIMIT 50;
Q: total deposits in 2024 and in 2025
SELECT SUM(amount) FILTER (WHERE EXTRACT(YEAR FROM txn_date) = 2024) AS deposits_2024, SUM(amount) FILTER (WHERE EXTRACT(YEAR FROM txn_date) = 2025) AS deposits_2025 FROM transactions WHERE txn_type = 'DEPOSIT';
Q: total deposits into BRAC Bank accounts in 2024
SELECT SUM(t.amount) AS total_deposits FROM transactions t JOIN user_accounts u ON u.account_id = t.account_id JOIN bank_information b ON b.bank_id = u.bank_id WHERE b.bank_name ILIKE '%brac%' AND t.txn_type = 'DEPOSIT' AND EXTRACT(YEAR FROM t.txn_date) = 2024;"""

RETRY_TEMPLATE = """Q: {question}
A previous attempt failed: {feedback}
Write a different, corrected query."""
