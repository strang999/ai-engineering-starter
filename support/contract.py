"""The Project Contract, version 1.2 (human-readable twin: CONTRACT.md).

Every lesson uses these names. Change one only as a versioned event:
bump CONTRACT_VERSION, update every lesson that uses the name, re-run the snippet tests.

Some types here (tools, agent loop, approvals) are used only from lessons 13-17.
They live here from tag l00 so nobody invents a different shape on the way.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTRACT_VERSION = "1.2"

# --- 2.2 Categories and tags (Ukrainian values, exactly these strings) ------

Category = Literal["доставка", "повернення", "обмін", "брак", "оплата", "акаунт", "інше", "невідомо"]
CATEGORIES: tuple[str, ...] = get_args(Category)

Tag = Literal["терміново", "повторне_звернення", "погроза_суду", "скарга"]
TAGS: tuple[str, ...] = get_args(Tag)

OrderStatus = Literal["new", "paid", "shipped", "delivered", "cancelled"]
ORDER_STATUSES: tuple[str, ...] = get_args(OrderStatus)


# --- 2.4 Ticket and card ------------------------------------------------------

class Ticket(BaseModel):
    ticket_id: str            # "T-0001"
    customer_id: str          # comes from the session, never from the model
    text: str
    created_at: str           # ISO 8601


class Fact(BaseModel):        # L08
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str | None         # None = unknown: not in the text
    evidence: str | None      # verbatim quote from the ticket


class TicketCard(BaseModel):  # what the MODEL returns (L08)
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Category
    category_evidence: str | None
    order_id: Fact
    amount: Fact              # money stays a string here, e.g. "1 250,00 грн"
    tags: list[Tag]


WHY_MAX = 300                         # chars kept from `why`; longer text is cut, never a schema error


class TicketCardReasoned(BaseModel):  # L09 `--prompt reason`: the same card, a short `why` written FIRST
    model_config = ConfigDict(extra="forbid", strict=True)
    # One short sentence: why this category. NOT evidence, NOT hidden reasoning: Anthropic lists a
    # `reasoning` / `thinking` field in JSON as a cause of the billed `reasoning_extraction` refusal and
    # allows "a short explanation". The limit lives in code: maxLength in the sent schema is a 400 on Claude.
    why: str | None = None
    category: Category
    category_evidence: str | None
    order_id: Fact
    amount: Fact
    tags: list[Tag]

    @field_validator("why")
    @classmethod
    def _short_why(cls, v: str | None) -> str | None:
        return v[:WHY_MAX] if v else v

    def to_card(self) -> TicketCard:
        """Drop `why`: it never reaches CardResult, the UI or the API (the raw reply stays in runs/)."""
        return TicketCard.model_validate_json(self.model_dump_json(exclude={"why"}))


CardStatus = Literal["ok", "needs_review", "empty_input", "refusal",
                     "schema_error", "truncated", "error"]


class CardResult(BaseModel):  # what OUR CODE returns to UI and evals
    status: CardStatus
    ticket_id: str
    card: TicketCard | None = None
    checks: dict[str, str] = {}     # field -> "accept" | "unknown" | "reject: ..."
    order_id: str | None = None     # normalized by code: "DEMO-1042"
    category: Category | None = None  # decided by code (rules L05 or checked card L08); None = «не знаю»
    amount_kop: int | None = None   # parsed by code, never by the model
    missing: list[str] = []         # e.g. ["order_id"]
    draft_reply: str | None = None  # L09+
    sources: list[str] = []         # L10+, chunk ids


class RagAnswer(BaseModel):   # L10
    model_config = ConfigDict(extra="forbid", strict=True)
    found: bool
    answer: str
    sources: list[str]


# --- Money: kopiyky as int, never float -------------------------------------

def format_kop(kop: int) -> str:
    """125000 -> '1 250,00 грн'. Refuses float and bool on purpose."""
    if isinstance(kop, bool) or not isinstance(kop, int):
        raise TypeError("money is int kopiyky, got " + type(kop).__name__)
    sign = "-" if kop < 0 else ""
    hryvni, kop_part = divmod(abs(kop), 100)
    grouped = f"{hryvni:,}".replace(",", " ")
    return f"{sign}{grouped},{kop_part:02d} грн"


# --- 2.6 Tools (used from L13) ------------------------------------------------

@dataclass(frozen=True)
class Ctx:
    customer_id: str
    ticket_id: str
    run_id: str


class ToolError(Exception):
    """Expected failure whose text the model may read."""


OrderId = Annotated[str, Field(pattern=r"^DEMO-[0-9]{4}$")]
DraftId = Annotated[str, Field(pattern=r"^RD-[0-9]{4}$")]
RefundReason = Literal["не_прийшло", "пошкоджено", "не_той_товар", "передумав"]


class _StrictArgs(BaseModel):
    # strict=True: "540" is NOT coerced to 540; extra="forbid": no customer_id from the model
    model_config = ConfigDict(extra="forbid", strict=True)


class GetOrderStatusArgs(_StrictArgs):
    order_id: OrderId


class CreateRefundDraftArgs(_StrictArgs):
    order_id: OrderId
    amount_kop: int = Field(gt=0)
    reason: RefundReason


class SearchKbArgs(_StrictArgs):
    query: str = Field(min_length=1, max_length=500)


class IssueRefundArgs(_StrictArgs):
    draft_id: DraftId         # the refund always points at an approved draft (fix for KeyError: 'draft_id')


class SendReplyArgs(_StrictArgs):
    text: str = Field(min_length=1, max_length=2000)


TOOL_ARGS: dict[str, type[BaseModel]] = {
    "get_order_status": GetOrderStatusArgs,
    "create_refund_draft": CreateRefundDraftArgs,
    "search_kb": SearchKbArgs,
    "issue_refund": IssueRefundArgs,
    "send_reply": SendReplyArgs,
}

POLICY: dict[str, Literal["allow", "confirm", "deny"]] = {
    "get_order_status": "allow",
    "create_refund_draft": "allow",
    "search_kb": "allow",
    "issue_refund": "confirm",
    "send_reply": "confirm",
}   # anything not listed: "deny"


def tool_parameters(name: str) -> dict:
    """JSON schema for a tool's arguments, generated from the strict pydantic model."""
    schema = TOOL_ARGS[name].model_json_schema()
    schema["additionalProperties"] = False
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


# --- 2.7 Agent loop (used from L14) -------------------------------------------

IntentName = Literal["статус", "повернення", "інше"]


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: IntentName


INTENT_TOOLS: dict[str, list[str]] = {
    "статус": ["get_order_status", "search_kb"],
    "повернення": ["get_order_status", "create_refund_draft"],
    "інше": [],
}


@dataclass
class Limits:
    max_steps: int = 5
    max_seconds: float = 60.0
    max_cost_usd: float = 0.05     # checked BEFORE each call using an estimate (L15)


@dataclass
class Step:
    n: int
    tool: str | None
    args: dict | None
    outcome: Literal["ok", "error", "denied", "waiting_approval"]
    cost_usd: float
    latency_ms: int


@dataclass
class AgentResult:
    status: Literal["answered", "handed_off", "waiting_approval"]
    text: str
    reason: str | None             # "step_limit", "time_limit", "budget_limit", "truncated", "refusal", "error", ...
    steps: list[Step] = field(default_factory=list)
    cost_usd: float = 0.0
    run_id: str = ""


# --- 2.8 Approvals and exactly-once (used from L15, L17) ----------------------

ActionStatus = Literal["waiting", "approved", "executing", "done", "failed", "denied", "expired"]


class Action(BaseModel):
    action_id: str                 # new_action_id(): random, never a hash of the args
    ticket_id: str
    tool: str
    args: dict                     # issue_refund args always carry draft_id
    args_hash: str                 # hash_args(args): stored separately, UNIQUE(ticket_id, tool, args_hash)
    status: ActionStatus
    proposed_by: str
    approved_by: str | None = None
    expires_at: str
    result: dict | None = None
    error: str | None = None


def new_action_id() -> str:
    """Random id: a re-proposal after expiry is a NEW action, a done action is never re-armed."""
    return uuid.uuid4().hex[:12]


def hash_args(args: dict) -> str:
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def idempotency_key(draft_id: str) -> str:
    """The payment key is tied to the draft, not to the attempt."""
    return f"refund-{draft_id}"
