"""Your own eval cases: evals/own.jsonl (CONTRACT.md, section 9).

    uv run python -m support.evals add-case "Де моя посилка? DEMO-1042" --category доставка --order-id DEMO-1042
    uv run python -m support.evals --baseline --tag own        # run only your cases

evals/cases.jsonl is the course's reference set: tags change it, the tests read it.
Your cases live only in evals/own.jsonl (ids own-01, own-02, ..., tag "own"), so carrying
them to the next lesson branch is one command: git checkout lesson-<NN-1> -- evals/own.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from support import STARTER_TAG
from support.config import ROOT
from support.contract import CATEGORIES

OWN_DEFAULTS = {"ticket_id": "T-OWN", "customer_id": "c-17"}
CARD_STATUSES = ("ok", "needs_review", "empty_input", "refusal", "schema_error", "truncated", "error")
ADD_HINT = 'uv run python -m support.evals add-case "текст" --category доставка'


def own_path() -> Path:
    """evals/own.jsonl; AIEZ_OWN_CASES points elsewhere (the tests use an empty temp file)."""
    return Path(os.environ.get("AIEZ_OWN_CASES") or ROOT / "evals" / "own.jsonl")


def _show(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_text(path: Path) -> tuple[str, str | None]:
    """-> (text, warning). UTF-8 is the format. Also reads what Windows writes by accident:
    a BOM, a whole file in UTF-16, and UTF-8 with lines appended as UTF-16 by PowerShell 5.1 `>>`."""
    data = path.read_bytes()
    name = _show(path)
    fix = f"Додавай кейси командою {ADD_HINT}, а не через >>."
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), f"увага: {name} збережено в UTF-16, а не в UTF-8. Прочитав. {fix}"
    if b"\x00" not in data:             # UTF-16 always has zero bytes here; UTF-8 JSON never does
        try:
            return data.decode("utf-8-sig"), None
        except UnicodeDecodeError:
            raise ValueError(f"{name} не в кодуванні UTF-8, і прочитати його не вдалося. "
                             f"Відкрий файл у редакторі, збережи як UTF-8 і повтори. {fix}") from None
    # UTF-8 first, then lines appended in UTF-16 LE (with or without a BOM) by `>>` in Windows PowerShell 5.1
    bom = data.find(b"\xff\xfe")
    start = bom if bom >= 0 else data.find(b"{\x00")
    try:
        if start < 0:
            raise UnicodeDecodeError("utf-8", data, 0, 1, "not utf-8")
        head = data[:start].decode("utf-8")
        tail = data[start:].decode("utf-16-le").lstrip("\ufeff")
    except UnicodeDecodeError:
        raise ValueError(f"{name} не в кодуванні UTF-8, і прочитати його не вдалося. "
                         f"Відкрий файл у редакторі, збережи як UTF-8 і повтори. {fix}") from None
    if head and not head.endswith(("\n", "\r")):
        head += "\n"
    return head + tail, f"увага: частину рядків {name} дописано в UTF-16 (так робить >> у Windows PowerShell 5.1). Прочитав. {fix}"


def parse_jsonl(text: str, name: str) -> list[dict]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name}, рядок {n}: це не JSON ({exc.msg}, символ {exc.colno})") from None
        if not isinstance(row, dict) or not row.get("id"):
            raise ValueError(f"{name}, рядок {n}: кожен рядок це JSON-об'єкт з полем \"id\"")
        rows.append(row)
    return rows


def read_jsonl(path: Path) -> list[dict]:
    text, warning = read_text(path)
    if warning:
        print(warning, file=sys.stderr)
    return parse_jsonl(text, _show(path))


def normalize(row: dict, name: str = "evals/own.jsonl") -> dict:
    """Fill what a learner may leave out: kind card, split dev, tag own, ticket_id and customer_id."""
    kind = row.get("kind", "card")
    field = "question" if kind in ("retrieval", "answer") else "text"          # lesson 10 kinds ask a question
    if not isinstance(row.get("input"), dict) or not isinstance(row["input"].get(field), str):
        raise ValueError(f"{name}, кейс {row['id']}: потрібне поле \"input\": {{\"{field}\": \"...\"}}")
    row.setdefault("kind", "card")
    row.setdefault("split", "dev")
    row.setdefault("expect", {})
    tags = row.get("tags") or []
    row["tags"] = tags + ["own"] if "own" not in tags else tags
    if row["kind"] == "card":
        for key, value in OWN_DEFAULTS.items():
            row["input"].setdefault(key, value)
    category = row["expect"].get("category")
    if category is not None and category not in CATEGORIES:
        print(f"увага: {row['id']}: категорії «{category}» нема в контракті ({', '.join(CATEGORIES)}), "
              f"цей кейс завжди падатиме", file=sys.stderr)
    return row


def load_own_cases(path: Path | None = None) -> list[dict]:
    """Your cases, or [] if the file does not exist yet."""
    path = path or own_path()
    if not path.is_file():
        return []
    return [normalize(r, _show(path)) for r in read_jsonl(path)]


def next_own_id(rows: list[dict]) -> str:
    nums = [int(m.group(1)) for r in rows if (m := re.fullmatch(r"own-(\d+)", str(r.get("id", ""))))]
    return f"own-{max(nums, default=0) + 1:02d}"


def _null(value: str | None):
    return None if value in ("null", "None", "") else value


def build_case(text: str, *, case_id: str, category: str | None = None, order_id: str | None = None,
               amount_kop: str | None = None, status: str | None = None, must_contain: list[str] | None = None,
               must_not_contain: list[str] | None = None, tags: list[str] | None = None, customer: str = "c-17",
               ticket_id: str | None = None, mock: str | None = None, split: str = "dev") -> dict:
    expect: dict = {}
    if status is not None:
        expect["status"] = status
    if category is not None:
        expect["category"] = _null(category)
    if order_id is not None:
        expect["order_id"] = _null(order_id)
    if amount_kop is not None:
        expect["amount_kop"] = None if _null(amount_kop) is None else int(amount_kop)
    if must_contain:
        expect["must_contain"] = must_contain if len(must_contain) > 1 else must_contain[0]
    if must_not_contain:
        expect["must_not_contain"] = must_not_contain if len(must_not_contain) > 1 else must_not_contain[0]
    row = {"id": case_id, "added_in": int(STARTER_TAG[1:]), "kind": "card", "split": split,
           "tags": ["own", *[t for t in (tags or []) if t != "own"]],
           "input": {"ticket_id": ticket_id or "T-" + case_id.replace("-", "").upper()[:8],
                     "customer_id": customer, "text": text},
           "expect": expect}
    if mock:
        row["mock"] = mock
    return row


def append_case(row: dict, path: Path | None = None) -> Path:
    """Append one row as UTF-8. A file broken by `>>` (UTF-16 parts) is rewritten whole in UTF-8."""
    path = path or own_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    if path.is_file() and path.stat().st_size:
        text, warning = read_text(path)
        if warning or path.read_bytes().startswith(b"\xef\xbb\xbf"):
            rows = parse_jsonl(text, _show(path))
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows) + line,
                            encoding="utf-8", newline="\n")
            return path
        prefix = "" if text.endswith("\n") else "\n"
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(prefix + line)
        return path
    path.write_text(line, encoding="utf-8", newline="\n")
    return path


def add_case_main(argv: list[str]) -> int:
    """uv run python -m support.evals add-case "текст" --category доставка --order-id DEMO-1042"""
    from support.llm.mock import SCENARIOS

    ap = argparse.ArgumentParser(prog="python -m support.evals add-case",
                                 description="Add one own case to evals/own.jsonl (UTF-8, next free own-NN id)")
    ap.add_argument("text", help="the ticket text, in quotes")
    ap.add_argument("--category", help=f"expected category: {', '.join(CATEGORIES)}, or null (must not decide)")
    ap.add_argument("--order-id", help="expected order id, e.g. DEMO-1042, or null")
    ap.add_argument("--amount-kop", help="expected amount in kopiyky (int), or null")
    ap.add_argument("--status", choices=CARD_STATUSES, help="expected CardResult status")
    ap.add_argument("--must-contain", action="append", default=[], help="text the reply draft must contain; repeat")
    ap.add_argument("--must-not-contain", action="append", default=[], help="text the reply draft must not contain")
    ap.add_argument("--tag", action="append", default=[], help="extra tag besides own; repeat")
    ap.add_argument("--customer", default="c-17", help="customer id (fictional): c-17, c-23 or c-99")
    ap.add_argument("--ticket", default=None, help="ticket id, default T-OWN01 for own-01")
    ap.add_argument("--id", default=None, help="case id, default the next own-NN")
    ap.add_argument("--mock", choices=SCENARIOS, default=None, help="mock scenario for this case")
    ap.add_argument("--split", default="dev", choices=["dev", "holdout"])
    args = ap.parse_args(argv)

    if args.category is not None and _null(args.category) is not None and args.category not in CATEGORIES:
        print(f"Категорії «{args.category}» нема в контракті. Можна: {', '.join(CATEGORIES)} або null.")
        return 2
    if args.amount_kop is not None and _null(args.amount_kop) is not None and not re.fullmatch(r"-?\d+", args.amount_kop):
        print("--amount-kop це ціле число копійок, напр. 54000 для 540,00 грн, або null.")
        return 2
    if not args.text.strip() and args.status is None:
        print("Порожній текст: додай --status empty_input, щоб кейс щось перевіряв.")
        return 2
    try:
        existing = load_own_cases()
        from support.evals import load_cases
        taken = {c["id"] for c in load_cases(own=True)}
    except ValueError as exc:
        print(f"Не можу прочитати кейси: {exc}")
        return 2
    case_id = args.id or next_own_id(existing)
    if case_id in taken:
        print(f"id {case_id} уже зайнятий. Візьми інший або не пиши --id.")
        return 2
    row = build_case(args.text, case_id=case_id, category=args.category, order_id=args.order_id,
                     amount_kop=args.amount_kop, status=args.status, must_contain=args.must_contain,
                     must_not_contain=args.must_not_contain, tags=args.tag, customer=args.customer,
                     ticket_id=args.ticket, mock=args.mock, split=args.split)
    path = append_case(row)
    print(f"додано {case_id} у {_show(path)}")
    print(json.dumps(row, ensure_ascii=False))
    if not row["expect"]:
        print("увага: жодного очікування, такий кейс завжди проходить. Додай --category, --order-id чи --status.")
    return 0


def add_question_main(argv: list[str]) -> int:
    """uv run python -m support.evals add-question "питання" --evidence "цитата з документа" (lesson 10)"""
    from support.rag import NOT_FOUND

    ap = argparse.ArgumentParser(prog="python -m support.evals add-question",
                                 description="Add one own retrieval/answer case to evals/own.jsonl")
    ap.add_argument("question", help="the question, in quotes")
    ap.add_argument("--evidence", help="the quote from your document that holds the answer")
    ap.add_argument("--no-answer", action="store_true", help="the knowledge base has no answer: expect «%s»" % NOT_FOUND)
    ap.add_argument("--kind", default="retrieval", choices=["retrieval", "answer"],
                    help="retrieval = hit@k only (default); answer = the model answers and the sources are checked")
    ap.add_argument("--tag", action="append", default=[], help="extra tag besides own; repeat")
    ap.add_argument("--id", default=None, help="case id, default the next own-NN")
    ap.add_argument("--split", default="dev", choices=["dev", "holdout"])
    args = ap.parse_args(argv)

    if not args.question.strip():
        print("Порожнє питання: пошук його не запускає, кейс нічого не перевіряв би.")
        return 2
    if bool(args.evidence) == bool(args.no_answer):
        print("Потрібне одне з двох: --evidence \"цитата\" або --no-answer.")
        return 2
    if args.no_answer and args.kind == "retrieval":
        print("Питання без відповіді перевіряє відповідь моделі: додай --kind answer.")
        return 2
    try:
        existing = load_own_cases()
        from support.evals import load_cases
        taken = {c["id"] for c in load_cases(own=True)}
    except ValueError as exc:
        print(f"Не можу прочитати кейси: {exc}")
        return 2
    case_id = args.id or next_own_id(existing)
    if case_id in taken:
        print(f"id {case_id} уже зайнятий. Візьми інший або не пиши --id.")
        return 2
    if args.no_answer:
        expect = {"found": False, "must_contain": NOT_FOUND}
    elif args.kind == "answer":
        expect = {"found": True, "evidence": args.evidence}
    else:
        expect = {"evidence": args.evidence}
    row = {"id": case_id, "added_in": int(STARTER_TAG[1:]), "kind": args.kind, "split": args.split,
           "tags": ["own", *[t for t in args.tag if t != "own"]], "input": {"question": args.question}, "expect": expect}
    path = append_case(row)
    print(f"додано {case_id} у {_show(path)}")
    print(json.dumps(row, ensure_ascii=False))
    return 0
