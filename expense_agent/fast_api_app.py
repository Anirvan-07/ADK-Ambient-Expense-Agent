from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Ambient Expense Agent")

class Expense(BaseModel):
    amount: float
    submitter: str
    category: str
    description: str
    date: str


@app.get("/")
def root():
    return {
        "status": "running",
        "agent": "ambient_expense_agent"
    }


from expense_agent.nodes import parse_event, route_expense

@app.post("/apps/expense_agent/trigger/pubsub")
async def pubsub_trigger(expense: Expense):

    parsed = parse_event(expense.dict())
    route_event = route_expense(parsed)

    return {
        "status": "processed",
        "amount": parsed.amount,
        "event_type": str(type(route_event)),
        "event": str(route_event)
    }