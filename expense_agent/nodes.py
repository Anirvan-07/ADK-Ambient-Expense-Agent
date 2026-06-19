# expense_agent/nodes.py
# ─────────────────────────────────────────────────────────────────────────────
# All workflow nodes and shared Pydantic data models.
#
# Node execution order (see agent.py for the wiring):
#
#   parse_event  →  route_expense
#                        ├─[route="auto"]────► auto_approve            (terminal)
#                        └─[route="review"]──► llm_risk_review
#                                                  └─► human_approval  (HITL)
#                                                            └─► record_outcome (terminal)
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncGenerator

from google import genai
from google.genai import types
from pydantic import BaseModel

from google.adk.agents.context import Context
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import FunctionNode

from .config import APPROVAL_THRESHOLD, MODEL


# ═══════════════════════════════════════════════════════════════════════════════
# Data models — shared across nodes; also act as the Workflow's I/O contracts.
# ═══════════════════════════════════════════════════════════════════════════════


class Expense(BaseModel):
    """Normalised expense record extracted from the incoming event."""

    amount: float
    submitter: str
    category: str
    description: str
    date: str


class _LlmAssessment(BaseModel):
    """Schema used only as the LLM's structured-output target.

    Kept internal (_) so callers work with RiskReport instead.
    """

    risk_level: str  # "low" | "medium" | "high"
    flags: list[str]
    summary: str


class RiskReport(BaseModel):
    """LLM risk assessment bundled together with the original expense."""

    expense: Expense
    risk_level: str
    flags: list[str]
    summary: str


class ApprovalOutcome(BaseModel):
    """Final decision, reviewer identity, and optional notes."""

    expense: Expense
    decision: str  # "approved" | "rejected"
    reviewer: str
    notes: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Node 1 — parse_event
# ═══════════════════════════════════════════════════════════════════════════════


def parse_event(node_input: dict) -> Expense:
    """Decode the incoming event payload and extract the Expense.

    Handles two shapes:
    • Real Pub/Sub: the message body sits under ``data`` as a base64 string.
    • Local test:   the dict is already the expense fields (no ``data`` key),
                    OR ``data`` is a plain-JSON string.

    Nothing is routed or scored here — pure data normalisation.
    """
    raw = node_input.get("data", node_input)

    if isinstance(raw, str):
        # Try base64 first (Pub/Sub wraps everything in base64).
        try:
            raw = json.loads(base64.b64decode(raw).decode())
        except Exception:
            # Fall back: treat as a plain JSON string.
            raw = json.loads(raw)

    return Expense(**raw)


# ═══════════════════════════════════════════════════════════════════════════════
# Node 2 — route_expense
# ═══════════════════════════════════════════════════════════════════════════════


def route_expense(node_input: Expense) -> Event:
    """Apply the dollar-threshold rule and set a routing signal.

    This is pure Python — no LLM, no I/O.
    Returns an Event that carries:
    • output  → the Expense (passed as node_input to the next node)
    • route   → "auto" or "review" (used by the conditional edges in agent.py)
    """
    route = "auto" if node_input.amount < APPROVAL_THRESHOLD else "review"
    return Event(output=node_input, route=route)


# ═══════════════════════════════════════════════════════════════════════════════
# Node 3a — auto_approve   (terminal node on the fast path)
# ═══════════════════════════════════════════════════════════════════════════════


async def auto_approve(node_input: Expense) -> AsyncGenerator[Event, None]:
    """Instantly approve low-value expenses; no LLM involved.

    Yields two events:
    1. A ``content`` event so the ADK web UI shows a confirmation message.
    2. An ``output`` event carrying the ApprovalOutcome for downstream use.
    """
    outcome = ApprovalOutcome(
        expense=node_input,
        decision="approved",
        reviewer="system",
        notes=(
            f"Auto-approved: ${node_input.amount:.2f} is below the "
            f"${APPROVAL_THRESHOLD:.0f} threshold."
        ),
    )
    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=(
                        f"✅ Auto-approved\n"
                        f"  Submitter: {node_input.submitter}\n"
                        f"  Amount:    ${node_input.amount:.2f}\n"
                        f"  Category:  {node_input.category}\n"
                        f"  {outcome.notes}"
                    )
                )
            ],
        )
    )
    yield Event(output=outcome)


# ═══════════════════════════════════════════════════════════════════════════════
# Node 3b — llm_risk_review   (only reached on the review path)
# ═══════════════════════════════════════════════════════════════════════════════


async def llm_risk_review(node_input: Expense) -> RiskReport:
    """Ask Gemini to assess risk factors for the expense.

    The LLM is only ever invoked here — nowhere else in the graph.
    Structured output (``response_schema``) ensures the response is
    parsed into ``_LlmAssessment`` directly, without fragile string parsing.
    """
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

    prompt = (
        "You are a corporate expense auditor.\n"
        "Analyse the expense below and return a structured risk assessment.\n\n"
        f"  Submitter:   {node_input.submitter}\n"
        f"  Amount:      ${node_input.amount:.2f}\n"
        f"  Category:    {node_input.category}\n"
        f"  Description: {node_input.description}\n"
        f"  Date:        {node_input.date}\n\n"
        "Identify risk factors such as: unusually high amount for the category, "
        "vague or missing description, potential policy violations, suspicious "
        "timing (weekend, holiday), duplicate-looking entries.\n"
        'Set risk_level to exactly one of: "low", "medium", "high".\n'
        "Return flags as a list of short strings (one per risk factor found)."
    )

    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_LlmAssessment,
        ),
    )

    assessment: _LlmAssessment = response.parsed  # type: ignore[assignment]

    # Bundle the original expense with the LLM's assessment into one object.
    return RiskReport(
        expense=node_input,
        risk_level=assessment.risk_level,
        flags=assessment.flags,
        summary=assessment.summary,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Node 4 — human_approval   (HITL — workflow pauses here)
# ═══════════════════════════════════════════════════════════════════════════════


async def _human_approval_impl(
    ctx: Context,
    node_input: RiskReport,
) -> AsyncGenerator[Event, None]:
    """Pause execution and wait for a human decision.

    First execution:
    • Emit a content event (shown in the UI) with the risk summary.
    • Yield a RequestInput — the workflow suspends until a human replies.

    On resume (ctx.resume_inputs contains the human's answer):
    • Reconstruct the ApprovalOutcome from the reply dict.
    • Emit a confirmation content event and an output event.

    Expected resume payload (send via the ADK web UI or API):
      {"decision": "approved" | "rejected", "reviewer": "<name>", "notes": "<opt>"}
    """
    interrupt_id = "expense_approval"
    resume = ctx.resume_inputs.get(interrupt_id)

    if resume is None:
        # ── First pass: show summary and pause ────────────────────────────────
        flag_text = "\n".join(f"  • {f}" for f in node_input.flags) or "  (none)"
        msg = (
            f"⏸️  Manual review required\n\n"
            f"  Submitter:  {node_input.expense.submitter}\n"
            f"  Amount:     ${node_input.expense.amount:.2f}\n"
            f"  Category:   {node_input.expense.category}\n"
            f"  Desc:       {node_input.expense.description}\n"
            f"  Risk level: {node_input.risk_level.upper()}\n"
            f"  Summary:    {node_input.summary}\n"
            f"  Flags:\n{flag_text}\n\n"
            f'Reply with:\n  {{"decision": "approved"|"rejected", '
            f'"reviewer": "<your name>", "notes": "<optional>"}}'
        )
        yield Event(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=msg)],
            )
        )
        # Yield the RequestInput — ADK converts it to an interrupt event and
        # suspends the workflow run.  The node is re-entered on resume because
        # rerun_on_resume=True is set on the FunctionNode wrapper below.
        yield RequestInput(
            interrupt_id=interrupt_id,
            message="Approve or reject this expense report.",
            response_schema=dict,  # any JSON object is fine
        )
        return

    # ── Resumed: process the human's decision ─────────────────────────────────
    decision = str(resume.get("decision", "rejected")).lower()
    reviewer = str(resume.get("reviewer", "unknown"))
    notes = str(resume.get("notes", ""))

    outcome = ApprovalOutcome(
        expense=node_input.expense,
        decision=decision,
        reviewer=reviewer,
        notes=notes,
    )
    icon = "✅" if decision == "approved" else "❌"
    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=(
                        f"{icon} {decision.capitalize()} by {reviewer}\n"
                        + (f"  Notes: {notes}" if notes else "")
                    )
                )
            ],
        )
    )
    yield Event(output=outcome)


# Wrap with rerun_on_resume=True so ADK re-enters this node after the human
# submits their answer, rather than forwarding the raw resume payload downstream.
human_approval = FunctionNode(
    func=_human_approval_impl,
    name="human_approval",
    rerun_on_resume=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Node 5 — record_outcome   (terminal node on the review path)
# ═══════════════════════════════════════════════════════════════════════════════


async def record_outcome(node_input: ApprovalOutcome) -> AsyncGenerator[Event, None]:
    """Persist / log the final decision and close the workflow run.

    In production this node would write to a database, send a Slack message,
    fire a Pub/Sub confirmation event, etc.  For now it emits a structured
    summary to the UI and forwards the serialised outcome as the final output.
    """
    icon = "✅" if node_input.decision == "approved" else "❌"
    yield Event(
        content=types.Content(
            role="model",
            parts=[
                types.Part.from_text(
                    text=(
                        f"📋 Expense report finalised\n"
                        f"  Decision:  {icon} {node_input.decision.upper()}\n"
                        f"  Submitter: {node_input.expense.submitter}\n"
                        f"  Amount:    ${node_input.expense.amount:.2f}\n"
                        f"  Category:  {node_input.expense.category}\n"
                        f"  Reviewer:  {node_input.reviewer}\n"
                        f"  Notes:     {node_input.notes or '—'}"
                    )
                )
            ],
        )
    )
    yield Event(output=node_input)
