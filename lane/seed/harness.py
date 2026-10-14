"""Seed harness. Identical starting point for both lanes. The evolve step may rewrite any of this.

Contract (fixed by the lane runner, must stay):
    solve(task, llm) -> str      Python source code that defines task["entry"]
    task = {"id", "entry", "prompt"}
    llm(system, messages, max_tokens) -> str   (raises BudgetExhausted when the budget is gone)
The harness may also run Python itself (e.g. subprocess) to test its own code before returning it.
"""
import re


def extract_code(text):
    blocks = re.findall(r"```(?:python)?\n(.*?)```", text, re.S)
    return blocks[-1] if blocks else text


def solve(task, llm):
    with open("prompt.md") as f:
        system = f.read()
    user = f"{task['prompt']}\n\nThe function must be named `{task['entry']}`."
    reply = llm(system, [{"role": "user", "content": user}], max_tokens=4000)
    return extract_code(reply)
