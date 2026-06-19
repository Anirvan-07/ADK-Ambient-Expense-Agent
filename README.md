# ADK Ambient Expense Agent

An event-driven AI Expense Approval Agent built using Google ADK 2.0, Gemini 2.5 Flash, FastAPI, and Human-in-the-Loop (HITL) workflows.

## Overview

This project demonstrates how an ambient AI agent can automatically process expense requests, route them through approval workflows, and involve human reviewers only when necessary.

The workflow combines:

- Google ADK 2.0 Workflow Graph
- Gemini 2.5 Flash
- FastAPI Trigger Endpoint
- Event-Driven Architecture
- Human-in-the-Loop Approval
- Rule-Based Routing

---

## Workflow Architecture

```text
START
  │
  ▼
parse_event
  │
  ▼
route_expense
  │
  ├── amount < $100
  │        ▼
  │   auto_approve
  │        ▼
  │      END
  │
  └── amount >= $100
           ▼
    llm_risk_review
           ▼
     human_approval
           ▼
     record_outcome
           ▼
           END
```

## Features

### Automatic Approval

Low-value expenses are approved instantly without invoking an LLM.

### AI Risk Assessment

High-value expenses are reviewed using Gemini 2.5 Flash.

### Human-in-the-Loop

Critical decisions can be escalated for human approval.

### FastAPI Trigger Endpoint

Expense events can be submitted through REST endpoints.

### Event-Driven Design

The system reacts to incoming events rather than waiting for user prompts.

---

## Tech Stack

- Python
- Google ADK 2.0
- Gemini 2.5 Flash
- FastAPI
- Pydantic
- Uvicorn

---

## API Endpoint

### Health Check

GET /

Response:

```json
{
  "status": "running",
  "agent": "ambient_expense_agent"
}
```

### Submit Expense

POST /apps/expense_agent/trigger/pubsub

Example:

```json
{
  "amount": 45,
  "submitter": "Anirvan",
  "category": "Travel",
  "description": "Bus fare",
  "date": "2026-06-19"
}
```

---

## Learning Outcomes

Through this project I learned:

- Agentic workflow design
- Event-driven AI systems
- Human-in-the-loop architectures
- FastAPI integration
- Workflow routing using Google ADK
- AI-assisted decision making

---

## Future Improvements

- Cloud Run Deployment
- Google Pub/Sub Integration
- Approval Dashboard
- Database Logging
- Slack Notifications
- Analytics Dashboard

---

## Author

Anirvan Mohapatra

B.Tech CSE (AI-ML)
Sri Sri University
