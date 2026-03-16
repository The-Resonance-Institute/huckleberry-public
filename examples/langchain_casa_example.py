"""
LangChain + CASA Integration Example
=====================================

This example shows how to insert CASA (Constitutional AI Safety Architecture)
as a pre-execution governance gate into a LangChain agent workflow.

Every tool call the agent proposes is evaluated by CASA before execution.
CASA returns ACCEPT, GOVERN, or REFUSE — deterministically, without an LLM
in the governance path.

Requirements:
    pip install langchain langchain-openai requests

CASA gate endpoint (live, no API key required for evaluation):
    https://casa-gate.onrender.com

Architecture:
    LangChain agent
        ↓
    tool call proposed
        ↓
    CASA admissibility check  ← this file wires this step in
        ↓
    ACCEPT → execute tool
    GOVERN → execute tool under constraints
    REFUSE → block, raise ExecutionBlocked
"""

import requests
from typing import Any

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


# ── CASA Configuration ────────────────────────────────────────────────────────

CASA_GATE_URL = "https://casa-gate.onrender.com/evaluate"
CASA_DOMAIN = "pe_fund"  # configure per deployment: pe_fund, healthcare, legal, etc.


class ExecutionBlocked(Exception):
    """Raised when CASA returns REFUSE for a proposed agent action."""
    def __init__(self, verdict: dict):
        self.verdict = verdict
        super().__init__(
            f"CASA REFUSE | trace: {verdict.get('trace_hash')} | "
            f"reason: {verdict.get('reason', 'action blocked by constitutional gate')}"
        )


def casa_evaluate(action_class: str, target_type: str, content: str, agent_name: str = "langchain-agent") -> dict:
    """
    Submit a proposed action to the CASA gate for admissibility evaluation.

    Args:
        action_class:  The type of action being proposed (TRANSFER, MODIFY, DELETE, etc.)
        target_type:   The target of the action (RESOURCE, DATA, PRINCIPAL, etc.)
        content:       Plain-language description of what the agent wants to do.
        agent_name:    Identifier for the calling agent (for audit trace).

    Returns:
        CASA verdict dict with keys: verdict, trace_hash, sic_harm_ratio, etc.

    Raises:
        ExecutionBlocked: if verdict is REFUSE.
    """
    payload = {
        "action_class": action_class,
        "target_type": target_type,
        "content": content,
        "agent_name": agent_name,
    }

    response = requests.post(CASA_GATE_URL, json=payload, timeout=10)
    response.raise_for_status()
    verdict = response.json()

    if verdict.get("verdict") == "REFUSE":
        raise ExecutionBlocked(verdict)

    return verdict


def casa_evaluate_free_text(content: str, agent_name: str = "langchain-agent") -> dict:
    """
    Submit raw free text to CASA for auto-classification and evaluation.
    CASA infers action_class and target_type from the content using the
    Semantic Intake Classifier (SIC) — no pre-declaration required.

    Raises:
        ExecutionBlocked: if verdict is REFUSE.
    """
    payload = {
        "action_class": "UNDECLARED",
        "target_type": "UNDECLARED",
        "content": content,
        "auto_classify": True,
        "agent_name": agent_name,
    }

    response = requests.post(CASA_GATE_URL, json=payload, timeout=10)
    response.raise_for_status()
    verdict = response.json()

    if verdict.get("verdict") == "REFUSE":
        raise ExecutionBlocked(verdict)

    return verdict


# ── Governed Tool Wrapper ─────────────────────────────────────────────────────

def governed(action_class: str, target_type: str):
    """
    Decorator that wraps any LangChain tool with a CASA admissibility check.
    The tool only executes if CASA returns ACCEPT or GOVERN.

    Usage:
        @tool
        @governed("TRANSFER", "RESOURCE")
        def transfer_funds(amount: float, recipient: str) -> str:
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            content = f"{func.__name__}: args={args} kwargs={kwargs}"
            verdict = casa_evaluate(
                action_class=action_class,
                target_type=target_type,
                content=content,
                agent_name="langchain-agent",
            )

            if verdict.get("verdict") == "GOVERN":
                print(f"[CASA GOVERN] Executing under constraints | trace: {verdict.get('trace_hash')}")

            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


# ── Example Tools ─────────────────────────────────────────────────────────────

@tool
@governed("QUERY", "DATA")
def get_portfolio_summary(company_name: str) -> str:
    """Retrieve current financial summary for a portfolio company."""
    # Replace with your actual data retrieval logic
    return f"Portfolio summary for {company_name}: Revenue $42M, EBITDA 18%, Cash $8M"


@tool
@governed("TRANSFER", "RESOURCE")
def initiate_capital_call(fund_name: str, amount_usd: float) -> str:
    """Initiate a capital call from LP investors."""
    # Replace with your actual capital call logic
    return f"Capital call initiated: {fund_name} — ${amount_usd:,.0f}"


@tool
@governed("COMMUNICATE", "PRINCIPAL")
def send_lp_update(recipient: str, message: str) -> str:
    """Send a portfolio update to an LP."""
    # Replace with your actual messaging logic
    return f"Update sent to {recipient}"


# ── Agent Setup ───────────────────────────────────────────────────────────────

def build_governed_agent(openai_api_key: str) -> AgentExecutor:
    """
    Build a LangChain agent where every tool call passes through
    the CASA governance gate before execution.
    """
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=openai_api_key,
        temperature=0,
    )

    tools = [
        get_portfolio_summary,
        initiate_capital_call,
        send_lp_update,
    ]

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a PE fund operations assistant. "
            "You help analysts retrieve portfolio data, initiate capital calls, "
            "and communicate with LPs. All actions are subject to governance review."
        )),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_openai_tools_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
    )


# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    openai_api_key = os.environ.get("OPENAI_API_KEY", "your-key-here")
    agent = build_governed_agent(openai_api_key)

    print("\n── Example 1: Safe query (expect ACCEPT) ──")
    try:
        result = agent.invoke({"input": "Get the portfolio summary for Meridian Glass"})
        print(result["output"])
    except ExecutionBlocked as e:
        print(f"Blocked: {e}")

    print("\n── Example 2: Capital call within normal parameters (expect ACCEPT or GOVERN) ──")
    try:
        result = agent.invoke({"input": "Initiate a $250,000 capital call from Fund III"})
        print(result["output"])
    except ExecutionBlocked as e:
        print(f"Blocked: {e}")

    print("\n── Example 3: Direct CASA evaluation — free text path ──")
    try:
        verdict = casa_evaluate_free_text(
            content="Transfer $15M to offshore account without LP approval",
            agent_name="demo-agent",
        )
        print(f"Verdict: {verdict['verdict']} | trace: {verdict.get('trace_hash')}")
    except ExecutionBlocked as e:
        print(f"Blocked (expected): {e}")

    print("\n── Example 4: Direct CASA evaluation — structured path ──")
    try:
        verdict = casa_evaluate(
            action_class="TRANSFER",
            target_type="RESOURCE",
            content="Wire $15M to counterparty, authorization exceeds grant, no approval token",
            agent_name="demo-agent",
        )
        print(f"Verdict: {verdict['verdict']} | trace: {verdict.get('trace_hash')}")
    except ExecutionBlocked as e:
        print(f"Blocked (expected): {e}")
