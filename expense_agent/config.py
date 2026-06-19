# expense_agent/config.py
# ─────────────────────────────────────────────────────────────────────────────
# Central configuration for the ambient expense-approval agent.
# Edit APPROVAL_THRESHOLD and MODEL here; they are imported by nodes.py and
# agent.py — nothing else needs touching for a simple threshold change.
# ─────────────────────────────────────────────────────────────────────────────

# Expenses BELOW this value are auto-approved with no LLM involvement.
# Expenses AT or ABOVE it go through LLM risk review + human approval.
APPROVAL_THRESHOLD: float = 100.0

# Gemini model used exclusively for the LLM risk-review step.
MODEL: str = "gemini-2.5-flash"
