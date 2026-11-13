"""Interactive terminal interface for the Bank Information Query Agent."""

import os

from colorama import Fore, Style, init

from agent.wrapper import BankQueryAgent
from database.build_db import build_database
from database.connection import check_db_health, get_db_cursor, get_safe_db_summary

init(autoreset=True)  # ANSI colours on Windows

BANNER = f"""{Fore.CYAN}{Style.BRIGHT}
==============================================================
            BANK INFORMATION QUERY AGENT
   Local LLM (Ollama) + SQL Generator + SQL Executor + Calculator
=============================================================={Style.RESET_ALL}
Type {Fore.YELLOW}help{Style.RESET_ALL} for commands, {Fore.YELLOW}exit{Style.RESET_ALL} to quit.
"""

HELP_TEXT = f"""
{Fore.CYAN}{Style.BRIGHT}Commands:{Style.RESET_ALL}
  {Fore.YELLOW}help{Style.RESET_ALL}         Show this guide
  {Fore.YELLOW}stats{Style.RESET_ALL}        Cache hits and model/token usage
  {Fore.YELLOW}cache clear{Style.RESET_ALL}  Forget cached answers
  {Fore.YELLOW}db status{Style.RESET_ALL}    Check PostgreSQL and record counts
  {Fore.YELLOW}db init{Style.RESET_ALL}      Rebuild the database (fixed seed)
  {Fore.YELLOW}clear{Style.RESET_ALL}        Clear the screen
  {Fore.YELLOW}exit{Style.RESET_ALL}         Quit

{Fore.CYAN}{Style.BRIGHT}Example questions:{Style.RESET_ALL}
  * How many active branches are in Dhaka?
  * Find the bank with routing number 200260123
  * What is the total balance of all SALARY accounts?
  * By what percent did total deposits grow from 2024 to 2025?
  * Show the 5 accounts with the highest balance
"""

LOG_COLORS = {"[Cache] HIT": Fore.GREEN, "[Cache] MISS": Fore.YELLOW, "[Guard]": Fore.MAGENTA,
              "[Step": Fore.MAGENTA, "[Tool: sql_generator]": Fore.BLUE, "[Tool: sql_executor]": Fore.CYAN,
              "[Tool: calculator]": Fore.CYAN, "[Verify]": Fore.GREEN, "[Status]": Fore.WHITE,
              "[Error]": Fore.RED}


def print_log(message: str) -> None:
    """Print one agent trace line in its colour."""
    color = next((c for tag, c in LOG_COLORS.items() if message.startswith(tag)), "")
    print(f"{color}{message}{Style.RESET_ALL}")


def handle_command(cmd: str, agent: BankQueryAgent) -> bool:
    """Run a built-in command. Returns False if the input is a question for the agent."""
    cmd = cmd.lower()
    if cmd in ("exit", "quit", "q"):
        raise SystemExit(0)
    if cmd == "help":
        print(HELP_TEXT)
    elif cmd == "clear":
        os.system("cls" if os.name == "nt" else "clear")
        print(BANNER)
    elif cmd in ("stats", "cache stats"):
        s, u = agent.cache.stats(), agent.usage
        print(f"\nCache: {s['total_keys']} entries, {s['hits']} hits, {s['misses']} misses "
              f"({s['hit_ratio_percent']}% hit ratio)")
        print(f"Model: {u['questions']} questions, {u['llm_calls']} calls, {u['tokens']} tokens\n")
    elif cmd == "cache clear":
        agent.cache.invalidate()
        print(f"{Fore.GREEN}Cache cleared.{Style.RESET_ALL}")
    elif cmd == "db status":
        try:
            with get_db_cursor() as cur:
                cur.execute("SELECT (SELECT COUNT(*) FROM bank_information) AS banks, "
                            "(SELECT COUNT(*) FROM user_accounts) AS accounts, "
                            "(SELECT COUNT(*) FROM transactions) AS txns")
                c = cur.fetchone()
            print(f"{Fore.GREEN}ONLINE{Style.RESET_ALL} {get_safe_db_summary()} - "
                  f"{c['banks']} branches, {c['accounts']} accounts, {c['txns']} transactions")
        except Exception as err:
            print(f"{Fore.RED}OFFLINE{Style.RESET_ALL} {get_safe_db_summary()} - {err}")
    elif cmd == "db init":
        try:
            counts = build_database()
            agent.cache.invalidate()  # cached answers may be stale after a rebuild
            print(f"{Fore.GREEN}Database rebuilt: {counts}{Style.RESET_ALL}")
        except Exception as err:
            print(f"{Fore.RED}Rebuild failed: {err}{Style.RESET_ALL}")
    else:
        return False
    return True


def main() -> None:
    """Health checks, then the read-eval-print loop."""
    print(BANNER)
    agent = BankQueryAgent()

    db_ok = check_db_health()
    print(f"[{Fore.GREEN + 'OK' if db_ok else Fore.RED + 'WARN'}{Style.RESET_ALL}] PostgreSQL "
          f"{get_safe_db_summary() if db_ok else 'unreachable - run: docker compose up -d'}")
    llm_ok = agent.llm.is_available()
    print(f"[{Fore.GREEN + 'OK' if llm_ok else Fore.RED + 'WARN'}{Style.RESET_ALL}] Ollama "
          f"{agent.llm.model if llm_ok else 'unreachable at ' + agent.llm.base_url}")
    if llm_ok:
        print("Loading model into memory...")
        agent.llm.warm_up()
    print()

    while True:
        try:
            # strip() + BOM removal: piped input on Windows can start with U+FEFF
            question = input(f"{Fore.GREEN}{Style.BRIGHT}You:{Style.RESET_ALL} ").strip().lstrip("﻿")
            if not question or handle_command(question, agent):
                continue
            result = agent.run(question, log_callback=print_log)
            if result["table"]:
                print(result["table"])
            print(f"\n{Style.BRIGHT}Agent:{Style.RESET_ALL} {result['response']}\n")
        except (KeyboardInterrupt, EOFError, SystemExit):
            print(f"\n{Fore.GREEN}Goodbye!{Style.RESET_ALL}")
            break


if __name__ == "__main__":
    main()
