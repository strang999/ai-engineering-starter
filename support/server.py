"""Local web service: the lesson 1 page, now backed by Python.

    uv run fastapi dev support/server.py      # http://127.0.0.1:8000, API docs at /docs

The model key, if any, lives only here (in .env on the server), never in web/.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from support.config import ROOT
from support.card import make_card
from support.contract import CardResult, Ticket
from support.data import connect, count_repeats, save_ticket
from support.rules import make_card_rules

app = FastAPI(title="Демо-маркет · support desk", version="1.0")

# A local frontend dev server (Vite on :5173 and the like) may call this service from the browser.
# Only localhost origins, any port; no cookies. A deployed app needs its own list of origins.
LOCAL_DEV_ORIGINS = r"^http://(localhost|127\.0\.0\.1)(:\d{1,5})?$"
app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_DEV_ORIGINS,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"], allow_credentials=False)

# In a real app the customer comes from the operator's session, never from the request body or the model.
DEMO_SESSION_CUSTOMER = "c-17"


class CardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")   # a customer_id in the body is refused, not trusted
    text: str = Field(max_length=4000)
    ticket_id: str | None = Field(default=None, pattern=r"^T-[A-Z0-9]{1,8}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")


@app.post("/api/card", response_model=CardResult)
def api_card(req: CardRequest, engine: Literal["model", "rules"] = "model") -> CardResult:
    """engine=model (lesson 8): the checked AI card; engine=rules: the lesson 3-5 baseline."""
    ticket_id = req.ticket_id or "T-" + uuid.uuid4().hex[:6].upper()
    ticket = Ticket(ticket_id=ticket_id, customer_id=DEMO_SESSION_CUSTOMER, text=req.text, created_at=_now())
    result = make_card(ticket) if engine == "model" else make_card_rules(ticket)
    if result.status != "empty_input":
        with connect() as conn:          # lesson 4: history for repeat tickets
            save_ticket(conn, ticket, result.order_id)
    return result


class RepeatsResponse(BaseModel):
    order_id: str
    repeats: int


@app.get("/api/repeats", response_model=RepeatsResponse)
def api_repeats(order_id: str = Query(pattern=r"^DEMO-[0-9]{4}$")) -> RepeatsResponse:
    with connect() as conn:
        return RepeatsResponse(order_id=order_id, repeats=count_repeats(conn, order_id, datetime.now(timezone.utc)))
