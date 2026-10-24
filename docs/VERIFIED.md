# What is verified, and where

Read on **2026-10-24**; refreshed the same day for contract 1.1 (workspace header, spend-limit errors, prompt caching, Gemini legacy status). "Verified" means seen on the provider's own page, in the SDK's source on PyPI/GitHub, or run offline in this repo. Nothing here was run against a live API: **no key was used**. Re-check prices and model ids before a lesson release; they change.

## Status of the live adapters

| Adapter | SDK checked | Offline proof in this repo | Live API |
|---|---|---|---|
| `support/llm/anthropic_.py` | `anthropic` 2.3.0 (2026-10-23) | request shape + mapping with fakes (`tests/test_adapters.py`); real SDK against a local stub server (`tests/test_adapters_sdk.py`): request accepted, sent with `anthropic-version: 2026-10-21`, top-level `cache_control` in the body and the `anthropic-workspace-id` header (24.10, contract 1.1), response parsed, 429 → `rate_limit` | **untested** |
| `support/llm/openai_.py` | `openai` 3.37.0 | same two test files; real SDK hits `POST /v1/responses`, cached tokens subtracted from input | **untested** |
| `support/llm/gemini_.py` | `google-genai` 2.33.0 | same two test files; real SDK hits `models/gemini-2.5-flash-lite:generateContent` with `responseJsonSchema`, 429 → `rate_limit` | **untested** |

`tests/test_adapters_sdk.py` is skipped unless the SDKs are installed:

```text
uv sync --extra anthropic --extra openai --extra gemini
uv run pytest tests/test_adapters_sdk.py -q
uv sync
```

What the offline proof does **not** cover, so check it on the first live run (lesson 6/7 release test): that each API accepts our JSON schema (`anyOf` with `null`, `enum`), that the default models exist for a new account, that `effort="low"` is accepted by the default model, that `max_output_tokens=1024` leaves room after thinking on Claude Haiku 5.5 (thinking is on by default there; a `max_tokens` stop maps to `truncated`), and the spend-cap errors used by `_common.error_code` (HTTP 402, or text matching «insufficient_quota», «credit balance» / «credit_balance», «billing», «spend limit» / «spend_limit», «spending cap», «usage limits»; the shapes come from the provider docs listed below, not from a live call).

## Call shapes

**Anthropic** (Messages API, Python SDK `anthropic`)
- `client.messages.create(model, max_tokens, system, messages, tools, output_config={"effort": ..., "format": {"type": "json_schema", "schema": ...}}, timeout)`; structured outputs take only `type` and `schema`; every object needs `additionalProperties: false`. Sources: https://platform.claude.com/docs/en/build-with-claude/structured-outputs ; SDK signature of `anthropic` 2.3.0 (installed and inspected).
- `stop_reason` values: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`, `model_context_window_exceeded` (the SDK's `Message.stop_reason` type in 2.3.0).
- Usage: `input_tokens` (without cache), `cache_read_input_tokens`, `cache_creation_input_tokens`, `output_tokens`.
- API version `2026-10-21` (sent by SDK 2.x) **removes `temperature`, `top_p`, `top_k` on every model**: sending one returns 400. Lesson 5 can say so plainly. Source: https://platform.claude.com/docs/en/api/versioning
- Claude Haiku 5.5: effort `low`…`max`, default `medium` (the adapter sets `low` explicitly); thinking is on by default. Source: claude-api reference (models table cached 2026-10-06) cross-checked with the pricing page below.
- Exceptions: `APITimeoutError`, `RateLimitError`, `APIStatusError`, `APIConnectionError`, `BadRequestError`, `AuthenticationError`, `PermissionDeniedError`, `InternalServerError` exist in 2.3.0 (inspected). The adapter sets `max_retries=0`: retries are `call_model`'s job.
- Workspace (checked 24.10): a key that is not scoped to a workspace must send `anthropic-workspace-id`, otherwise 400 `invalid_request_error`. The adapter sends it when `ANTHROPIC_WORKSPACE_ID` is set in `.env`; a key created inside a workspace needs nothing. Key expiration presets: 3 h, 1 d, 7 d, 30 d, custom, Never. Source: https://platform.claude.com/docs/en/manage-claude/authentication
- Spend limits (checked 24.10): your own limit (Billing → Spend limits) answers 400 «You have reached your specified API usage limits»; the tier cap (Start $500, Build $1,000, Scale $200,000) answers 429 `rate_limit_error` with `enforced_spend_limit_reached` and no `retry-after`. Both map to `spend_cap` and are never retried. The Default workspace has no spend limit. Source: https://platform.claude.com/docs/en/api/rate-limits
- Prompt caching (checked 24.10): top-level `cache_control: {"type": "ephemeral"}` turns on automatic caching (the `messages.create` signature in SDK 2.3.0 has the parameter); minimum cacheable prompt 512 tokens on Haiku 5.5, shorter prompts are processed without caching and without an error; usage reports `cache_read_input_tokens` and `cache_creation_input_tokens`. A 5-minute cache write costs 1.25× the input price, a read 0.1×. The adapter sends `cache_control` on every request (`AIEZ_ANTHROPIC_CACHE=0` turns it off) and passes writes as `Usage.cache_write_tokens`, priced in `prices.estimate_usd`. Today's card and reply prompts are under 512 tokens, so `cached` stays 0 in lessons 6–9. Source: https://platform.claude.com/docs/en/build-with-claude/prompt-caching

**OpenAI** (Responses API, Python SDK `openai`)
- `client.responses.create(model, instructions, input, max_output_tokens, reasoning={"effort": ...}, text={"format": {"type": "json_schema", "name", "schema", "strict": True}}, tools=[{"type": "function", "name", "description", "parameters", "strict"}], timeout)`. Sources: https://github.com/openai/openai-python/blob/main/src/openai/resources/responses/responses.py , https://developers.openai.com/api/reference/resources/responses/methods/create
- Response: `status` (`completed`, `incomplete`, `failed`, …), `incomplete_details.reason` (`max_output_tokens`, `content_filter`, …), `output` items `message` (parts `output_text` / `refusal`) and `function_call` (`call_id`, `name`, `arguments` as a JSON string); tool results go back as `{"type": "function_call_output", "call_id", "output"}`.
- Usage: `input_tokens` **includes** `input_tokens_details.cached_tokens` (the adapter subtracts it); `output_tokens` includes reasoning tokens.
- Key: `OPENAI_API_KEY`. The SDK retries 2 times by default; the adapter sets `max_retries=0`.
- Spend limits (checked 24.10): Project settings → Limits → «Enforce a hard limit»; a project over its limit gets 429 `project_spend_limit_exceeded`, an empty prepaid balance `credit_balance_exhausted`. Both map to `spend_cap`. Source: https://developers.openai.com/api/docs/guides/spend-limits

**Google Gemini** (Python SDK `google-genai`)
- `genai.Client(api_key=...)`; `client.models.generate_content(model, contents, config={"system_instruction", "max_output_tokens", "response_mime_type": "application/json", "response_json_schema", "tools": [{"function_declarations": [...]}], "thinking_config", "http_options": {"timeout": <ms>, "retry_options": {"attempts": 1}}})`. Sources: https://github.com/googleapis/python-genai (README, `types.py`), https://ai.google.dev/gemini-api/docs/generate-content/structured-output (page updated 2026-10-19).
- Google now titles the generateContent pages «Gemini Generate Content API (Legacy)»; the newer docs show `client.interactions.create(...)`. Checked 24.10: the Interactions API is the default since June 2026; `generateContent` is «now considered legacy» but «remains fully supported»; `gemini-2.5-flash-lite` has no shutdown date (deprecations page updated 2026-10-22). The adapter keeps the documented `generateContent` call. Sources: https://ai.google.dev/gemini-api/docs/migrate-to-interactions , https://ai.google.dev/gemini-api/docs/deprecations
- Billing (checked 24.10): the paid tier needs a linked billing account and a prepay (minimum $5); with the prepaid balance at $0 the API answers HTTP 402, which maps to `spend_cap`. Project spend caps live on the AI Studio Spend page («experimental», billing data up to ~10 min late). Source: https://ai.google.dev/gemini-api/docs/billing (updated 2026-09-28)
- Thinking: 2.5 models take `thinking_budget` (`0` turns it off on 2.5 Flash / Flash-Lite); 3.x take `thinking_level` (`LOW`, `MEDIUM`, `HIGH`; 3.x Flash-Lite cannot turn thinking fully off). Source: https://ai.google.dev/gemini-api/docs/generate-content/thinking (updated 2026-10-14).
- Response: `candidates[0].finish_reason` (`STOP`, `MAX_TOKENS`, `SAFETY`, `RECITATION`, …), `prompt_feedback.block_reason`, `function_calls`, `usage_metadata.prompt_token_count` (includes `cached_content_token_count`, subtracted), `candidates_token_count` + `thoughts_token_count` (added).
- Key: `GEMINI_API_KEY` or `GOOGLE_API_KEY` (if both are set, the SDK prefers `GOOGLE_API_KEY`). Errors: `google.genai.errors.APIError` / `ClientError` / `ServerError` with `.code`.
- Not verified: sending the tool-call `id` back inside `function_response` is read from the SDK source (`FunctionResponse.id`), not from a doc.

## Default models and prices (`support/prices.py`)

USD per 1M tokens, standard tier.

| Provider | Default model | Input | Cached input | Output | Source | Caveat |
|---|---|---|---|---|---|---|
| anthropic | `claude-haiku-5-5` | 0.10 | 0.01 | 0.50 | https://platform.claude.com/docs/en/about-claude/pricing | prompts up to 100,000 tokens; above: 0.50 / 0.05 / 2.50 (in `prices.LONG_PROMPT`) |
| openai | `gpt-6-luna` | 0.10 | 0.01 | 0.50 | https://developers.openai.com/api/docs/pricing , https://developers.openai.com/api/docs/models/gpt-6-luna | cheapest model **not** marked deprecated; the page does not say GA or preview (not verified). Cache writes cost extra ($0.125 for 30 min). `gpt-5-nano` and `gpt-5.4-nano` are cheaper or similar but marked «Deprecated». |
| gemini | `gemini-2.5-flash-lite` | 0.10 | 0.01 | 0.40 | https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/models | paid tier; a free tier exists and its data «Used to improve our products: Yes». Context-cache storage ($1.00 per 1M tokens per hour) is not modelled. |

Also priced for lesson 7 comparisons: `claude-sonnet-5-5` (2.00 / 0.10 / 10.00), `claude-opus-5-5` (4.00 / 0.20 / 20.00), `gpt-5.6-luna` (0.20 / 0.02 / 1.20), `gemini-3.1-flash-lite` (0.25 / 0.025 / 1.50, «Stable»).

The spec asks for «the cheapest current model that passes the L07 run». These defaults are the cheapest current models by price only; **no L07 run has been made on a live provider**, so «passes» is not verified.

## Other facts used in the repo

| Fact | Where used | Source / proof |
|---|---|---|
| `UnicodeEncodeError: 'charmap'` when Python prints Ukrainian to a piped stdout on Windows; `PYTHONUTF8=1` fixes it | `scripts/doctor.py`, `config.setup_console()`, README | reproduced on this machine (Windows 11, Python 3.10, cp1252) while building the repo; persona reviews 2026-10-24 |
| uv install via `winget install --id=astral-sh.uv -e` | README, doctor hints | spec section 3 «Windows notes»; not re-run on a clean machine here |
| `tiktoken` `o200k_base`: «Хочу повернути гроші за замовлення 1042» = 13 tokens | `support/tokens.py` (optional extra) | run here with `uv sync --extra tokens`; the first run downloads the vocabulary file |
| FastAPI dev server on `http://127.0.0.1:8000` with `/docs` | README, `support/server.py` | `uv run fastapi dev support/server.py` started and answered `POST /api/card` here |
