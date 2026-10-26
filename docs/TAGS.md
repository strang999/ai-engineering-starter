# Tags

Tag `lNN` = the state at the **end** of lesson NN (the reference solution); `git diff l07 l08` is exactly what lesson 8 adds. Linear history, one commit per tag. Contract 1.1 (24.10.2026) rebuilt the history: every 1.1 change sits on the earliest tag it belongs to (CONTRACT.md, section 12). Contract 1.2 (same day) changed only `l09` (prompting techniques, CONTRACT.md section 13); `l00`–`l08` stay on 1.1.

One branch per lesson, `lesson-NN`. Lesson 0 starts from `l00`; lessons 1–4 (you build) from `l(NN-1)`; from lesson 5 on (you read, run and extend) from `lNN`. Own cases live in `evals/own.jsonl` and move with one command:

```text
git switch -c lesson-06 l06
git checkout lesson-05 -- evals/own.jsonl
uv sync
uv run pytest -q
```

Test counts below were recorded on 2026-10-24 (contract 1.1) with `git checkout lNN && uv sync && uv run pytest -q` on Windows 11, Python 3.12.12, uv 0.9.16, mock mode, no key, no network for the tests. «skipped» = `tests/test_adapters_sdk.py`, which runs only after `uv sync --extra anthropic --extra openai --extra gemini` (3 passed that way at `l06`). Every tag also passes `uv run python scripts/check_snippets.py --all` on the repo's own docs (3/3 blocks). `requirements.txt` on every tag is `uv export` of that tag's `uv.lock` (pip path).

| Tag | What it adds | Tests | Try it |
|---|---|---|---|
| `l00` | skeleton, contract types v1.0 (`support/contract.py`), mock `call_model` with 17 scenarios, `scripts/doctor.py`, demo, snippet harness, AGENTS/CLAUDE/KB/STATE, empty `evals/own.jsonl`, `scripts/carry_own_cases.py`, `requirements.txt` | 40 passed | `uv run python scripts/doctor.py` · `uv run python -m support.demo` |
| `l01` | browser prototype `web/index.html` (open by double click), feature + 3 checks in `KB.md` | 42 passed | double-click `web/index.html` |
| `l02` | skill `pre-commit-check` in `.agents/skills/` and `.claude/skills/` | 43 passed | ask your assistant «перевір перед комітом» |
| `l03` | `support/rules.py` (`normalize_order_id`, `make_card_rules`), FastAPI service, page calls `POST /api/card`, cases `c001`–`c003`, `run_evals --baseline`, own cases (`--tag own`, `add-case`), `--id`, localhost CORS | 73 passed | `uv run fastapi dev support/server.py` · `uv run python -m support.evals --baseline` |
| `l04` | SQLite `tickets`, `count_repeats(conn, order_id, now)`, `specs/repeat-tickets.md`, `tests/test_repeats.py`, Cyrillic look-alikes, `GET /api/repeats` | 82 passed | `uv run pytest tests/test_repeats.py -q` |
| `l05` | `triage_rules` (abstains with `None`), 30 labelled cases `c001`–`c030`, `demo` subset, `support.tokens` | 94 passed | `uv run python -m support.evals --baseline --tag demo` · `uv run python -m support.tokens "Хочу повернути гроші за замовлення 1042"` |
| `l06` | live adapters (Anthropic, OpenAI, Gemini; untested live), `prices.py`, one retry, `runs/calls.jsonl`, first `make_card` (trusts the model), `support.llm` first-call CLI, `docs/VERIFIED.md` | 142 passed, 3 skipped | `uv run python -m support.llm --save runs/first-call.json` · `uv run python -m support.llm --scenario timeout` |
| `l07` | `run_evals` model path, several `--model`s with a comparison table, `--dry-run`, `--runs`, `--effort`, `--max-usd`, `model-choice.md` | 152 passed, 3 skipped | `uv run python -m support.evals` · `uv run python -m support.evals --model mock:mock-1 --model anthropic:claude-haiku-5-5 --dry-run` |
| `l08` | `check_fact`, category evidence check, `parse_amount_kop`, `needs_review`, one repeat on `schema_error`, 8 `contract` edge cases `c031`–`c038`, `/api/card?engine=model` | 168 passed, 3 skipped | `uv run python -m support.evals --tag contract` |
| `l09` | `support/context.py`: `update_customer_state`, reply draft chain `make_card_with_reply`, prompt variant `B`, `--variant`, 5 `context` cases `c039`–`c043`, order-owner check (`c041` → `needs_review`); contract 1.2: `--prompt zero\|one\|few\|reason`, `evals/examples.jsonl` + `examples_bias.jsonl`, `--examples`, `--reverse-examples`, `TicketCardReasoned`, prompt-aware mock, `--runs N --vote` | 195 passed, 3 skipped | `uv run python -m support.evals --tag context --variant B` · `uv run python -m support.context c-17` · `uv run python -m support.evals --prompt few --tag demo` |
| `l10` | `data/kb/` (7 policy files + `archive/`), `support/rag/` (`split_doc`, `keyword_search`, `vector_search`, `hybrid_search`, `search_kb`, `answer_from_kb`, `check_answer`), `embed()` with routes mock / local / openai / gemini, `data/kb_vectors.npz` (real e5 vectors for the course texts), mock `purpose="rag"` + 3 scenarios, cases `r001`–`r016` and `a001`–`a017`, `--kind retrieval\|answer --mode --k --chunk-size --kb`, `add-question`, `POST /api/answer` | 235 passed, 3 skipped | `uv run python -m support.evals --kind retrieval --mode all --tag happy` · `uv run python -m support.evals --kind answer` |

## Eval numbers per tag (mock, for lesson writers)

| Tag | Command | Output |
|---|---|---|
| `l03` | `--baseline` | pass 3/3 |
| `l05` | `--baseline` | pass 17/30 · coverage 18/29 · precision 16/18 |
| `l05` | `--baseline --tag demo` | pass 3/10 · coverage 4/10 · precision 3/4 |
| `l07` | (model, mock) | pass 27/30 · coverage 29/29 · precision 26/29 |
| `l08` | (model, mock) | pass 35/38 · coverage 29/30 · precision 27/29; `--tag contract` 8/8 |
| `l09` | (model, mock) | pass 39/43 · coverage 30/31 · precision 28/30; `--tag context` A 4/5, B 5/5 |
| `l09` | `--prompt zero` / `one` / `few` / `reason` | pass 39/43 / 40/43 / 42/43 / 40/43 |
| `l09` | same, `--tag demo` | pass 7/10 / 8/10 / 10/10 / 8/10 |
| `l09` | `--prompt few --reverse-examples` | pass 41/43 (c011 flips back to `невідомо`) |
| `l09` | `--prompt few --examples evals/examples_bias.jsonl` | pass 37/43 · precision 26/31 (5 ambiguous tickets → `обмін`) |
| `l10` | `--kind retrieval --mode all --tag happy` (10 questions, 7 chunks) | keyword 9/10 · 10/10; vector 10/10 · 10/10; hybrid 9/10 · 10/10 (hit@1 · hit@3) |
| `l10` | same, `--chunk-size 200` (20 chunks) | keyword 8/10 · 9/10; vector 9/10 · 10/10; hybrid 8/10 · 10/10 |
| `l10` | `--kind retrieval --mode all` (all 16 incl. edge) | keyword 11/16 · 13/16; vector 15/16 · 16/16; hybrid 13/16 · 16/16 |
| `l10` | `--kind answer` (mock) | pass 16/17; a017 fails on purpose (`answers_without_basis`) |

The `l10` retrieval numbers are real: the vectors in `data/kb_vectors.npz` come from multilingual-e5-small and the table matches a run of the lesson's own code on that model (24.10). The mock fails c011, c021 and c025 on purpose (fixtures in `fixtures/mock_replies.jsonl`), so lesson 7 has failures to read. From `l09` the mock also reacts to examples and the short `why` field by three fixed rules (CONTRACT.md 11.14), so lesson 9 can show the zero → one → few ladder offline.
