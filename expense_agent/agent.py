# expense_agent/agent.py
# ─────────────────────────────────────────────────────────────────────────────
# Wires all nodes into the ADK 2.0 Workflow graph.
#
# Graph topology (→ = unconditional edge, ─[x]→ = edge taken when route == x):
#
#   START
#     → parse_event
#       → route_expense
#           ─[auto]──► auto_approve      (terminal — fast path)
#           ─[review]► llm_risk_review
#                         → human_approval   (HITL pause)
#                             → record_outcome   (terminal — review path)
#
# The routing decision (auto vs review) is made entirely in Python inside
# route_expense; the LLM is only invoked inside llm_risk_review.
# ─────────────────────────────────────────────────────────────────────────────

from google.adk.workflow import Edge, START, Workflow

from .nodes import (
    auto_approve,
    human_approval,   # FunctionNode instance (rerun_on_resume=True)
    llm_risk_review,
    parse_event,
    record_outcome,
    route_expense,
)

# ── Graph definition ──────────────────────────────────────────────────────────
#
# Edges are listed in execution order for readability.
#
# Unconditional edges use plain tuples: (from_node, to_node)
# Conditional edges use Edge(from_node=..., to_node=..., route=<value>)
#   — the edge is followed when the upstream node emits Event(route=<value>).
#
# Nodes with no outgoing edges (auto_approve, record_outcome) are terminal:
# the Workflow considers the run complete when they finish.

root_agent = Workflow(
    name="expense_approval",
    edges=[
        # ── Ingress: decode and normalise the incoming event ──────────────────
        (START, parse_event),

        # ── Threshold check: sets route to "auto" or "review" ─────────────────
        (parse_event, route_expense),

        # ── Fast path (amount < APPROVAL_THRESHOLD) ───────────────────────────
        Edge(from_node=route_expense, to_node=auto_approve, route="auto"),

        # ── Review path (amount >= APPROVAL_THRESHOLD) ────────────────────────
        Edge(from_node=route_expense, to_node=llm_risk_review, route="review"),

        # LLM assessment → HITL pause → record final decision
        (llm_risk_review, human_approval),
        (human_approval, record_outcome),

        # auto_approve and record_outcome are terminal (no outgoing edges).
    ],
)
