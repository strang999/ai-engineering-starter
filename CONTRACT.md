# Контракт проєкту · версія 1.2

Одна сторінка імен, даних і форматів, однакова для всіх уроків курсу «AI Engineering з нуля». Код: `support/contract.py` (типи), `support/llm/__init__.py` (`call_model`).

Зміна контракту це подія з версією: підвищити `CONTRACT_VERSION`, оновити кожен урок, що використовує змінене ім'я, перезапустити snippet-тести (`docs/SNIPPETS.md`).

`CONTRACT_VERSION = "1.2"`. Що змінилось від 1.0: розділ 12; від 1.1: розділ 13. Теги `l00`–`l08` лишаються на 1.1: версія 1.2 додає тільки урок 9 (тег `l09`).

## 1. Домен

**«Демо-маркет»**: невеликий український інтернет-магазин (одяг, взуття, косметика), гроші в гривнях. Ми будуємо інструмент оператора для звернень клієнтів: картка на звернення, потім AI-картка з перевіркою доказів, відповідь за політикою магазину й агент, який перевіряє замовлення та готує чернетку повернення, яку погоджує людина.

Інструмент нічого не надсилає клієнту без оператора й не рухає гроші без підтвердження. Фінтех, бухгалтерія та інші ніші з'являються тільки в блоках «У твоєму проєкті».

## 2. Категорії й теги

Категорія (рівно ці рядки, `Category` у коді):

| Значення | Коли |
|---|---|
| `доставка` | де посилка, затримка, кур'єр, адреса |
| `повернення` | хоче гроші назад за замовлення |
| `обмін` | інший розмір чи колір |
| `брак` | товар прийшов пошкодженим чи з дефектом |
| `оплата` | списання, оплата не проходить, код помилки, рахунок |
| `акаунт` | вхід, пароль, особисті дані, підписка |
| `інше` | текст зрозумілий, але не підходить під жодну з вище |
| `невідомо` | з тексту не видно, чого хоче клієнт |

Теги (нуль або більше, `Tag`): `терміново`, `повторне_звернення`, `погроза_суду`, `скарга`.

Правила-baseline (урок 5) можуть **утриматися**: `triage_rules` повертає `None`, у звіті це «не знаю». Утримання не категорія; воно рахується в покритті (coverage) і точності (precision).

## 3. Демо-дані

Клієнти: `c-17`, `c-23`, `c-99` (тільки id, без імен).

Замовлення, `data/orders.json`, гроші в копійках (`int`):

| order_id | customer_id | status | total_kop | refunded_kop | delivered_at |
|---|---|---|---|---|---|
| `DEMO-1042` | c-17 | `shipped` | 120000 | 0 | null |
| `DEMO-1043` | c-17 | `delivered` | 54000 | 0 | 2026-10-20 |
| `DEMO-1044` | c-17 | `paid` | 89990 | 0 | null |
| `DEMO-1045` | c-17 | `cancelled` | 25000 | 25000 | null |
| `DEMO-1050` | c-23 | `delivered` | 149900 | 50000 | 2026-10-12 |
| `DEMO-2001` | c-99 | `delivered` | 300000 | 0 | 2026-10-18 |

Статуси: `new`, `paid`, `shipped`, `delivered`, `cancelled`. Інтерфейс показує копійки як `1 200,00 грн` (`format_kop`). `float` для грошей ніде не використовується. Чуже замовлення виглядає так само, як неіснуюче.

Звернення: `data/tickets.jsonl`, 30 штук `T-0001`…`T-0030`, з тегу `l00`. Розмітка категорій для них з'являється в `evals/cases.jsonl` у тезі `l05`.

## 4. Звернення і картка

```python
# Це схема з support/contract.py, не окремий код для запуску
class Ticket(BaseModel):
    ticket_id: str            # "T-0001"
    customer_id: str          # з сесії, ніколи від моделі
    text: str
    created_at: str           # ISO 8601

class Fact(BaseModel):        # extra="forbid", strict
    value: str | None         # None = невідомо: у тексті нема
    evidence: str | None      # дослівна цитата зі звернення

class TicketCard(BaseModel):  # що повертає МОДЕЛЬ (extra="forbid", strict)
    category: Category
    category_evidence: str | None
    order_id: Fact
    amount: Fact              # сума тут рядок, напр. "1 250,00 грн"
    tags: list[Tag]

class TicketCardReasoned(BaseModel):  # з l09, для --prompt reason (extra="forbid", strict)
    why: str | None = None            # одне коротке речення ДО відповіді: чому ця категорія; не доказ;
                                      # код обрізає до WHY_MAX = 300 знаків (maxLength у схемі Claude не приймає)
    category: Category                # далі ті самі поля, що в TicketCard
    category_evidence: str | None
    order_id: Fact
    amount: Fact
    tags: list[Tag]
    def to_card(self) -> TicketCard: ...   # відкидає why

CardStatus = Literal["ok", "needs_review", "empty_input", "refusal",
                     "schema_error", "truncated", "error"]

class CardResult(BaseModel):  # що повертає НАШ КОД інтерфейсу й evals
    status: CardStatus
    ticket_id: str
    card: TicketCard | None = None
    checks: dict[str, str] = {}       # поле -> "accept" | "unknown" | "reject: ..."
    order_id: str | None = None       # нормалізує код: "DEMO-1042"
    category: Category | None = None  # вирішує код (правила або перевірена картка); None = «не знаю»
    amount_kop: int | None = None     # парсить код, ніколи модель
    missing: list[str] = []           # напр. ["order_id"]
    draft_reply: str | None = None    # з уроку 9
    sources: list[str] = []           # з уроку 10
```

Версії картки:

| Версія | Тег | Що є |
|---|---|---|
| v1 | `l01` (браузер) | текст, номер замовлення або «Номер не надано», чого бракує |
| v1 | `l03` (Python) | `CardResult(status, ticket_id, order_id, missing)` від `make_card_rules` |
| v2 | `l05` | + `category` від правил або утримання |
| v3 | `l06` | `make_card` питає модель: `card`, `category` без перевірок (перший виклик) |
| v3 | `l08` | + `checks`, `amount_kop`, `needs_review`: кожне значення перевірене цитатою |
| v4 | `l09` | + `draft_reply` |
| v5 | `l10` | + `sources` |

Спільні функції (вводяться один раз, далі тільки за назвою):

| Ім'я | Тег | Сигнатура |
|---|---|---|
| `normalize_order_id` | `l03`, розширено `l04` | `(raw: str) -> str \| None`: пробіли, регістр, `DEMO 1042` → `DEMO-1042`, з `l04` кириличні двійники, >30 символів → None |
| `make_card_rules` | `l03` | `(ticket: Ticket) -> CardResult` |
| `count_repeats` | `l04` | `(conn, order_id: str, now: datetime) -> int` |
| `triage_rules` | `l05` | `(text: str) -> Category \| None` |
| `build_card_prompt` | `l06`, варіант `B` і техніка `prompt` у `l09` | `(ticket: Ticket, variant: str = "A", prompt: str = "zero", examples: list[dict] \| None = None) -> list[dict]`; системна роль окремо: `CARD_SYSTEM`. `prompt`: `zero` (як було), `one` / `few` (1 / 3 перші приклади в `<examples>` перед `<ticket>`), `reason` (коротке поле `why` першим) |
| `make_card` | `l06`, перевірки `l08`, `prompt` у `l09` | `(ticket: Ticket, *, variant: str = "A", prompt: str = "zero", examples: list[dict] \| None = None) -> CardResult`; з `prompt="reason"` просить `TicketCardReasoned` і відкидає `why` до перевірок: у `CardResult`, UI й API його нема, сира відповідь лишається в `runs/` |
| `load_examples` | `l09` | `(path=None) -> list[dict]`: рядки `evals/examples.jsonl`, кожна `card` валідна як `TicketCard` |
| `parse_amount_kop` | `l08` | `(raw: str) -> int \| None`: «1 250,00 грн» → 125000; «-1250.00» → -125000 (знак зберігається, сума ≤ 0 відхиляє `make_card`); «півтори тисячі» → None |
| `check_fact` | `l08` | `(fact: Fact, source: str) -> str` |
| `update_customer_state` | `l09` | `(state: dict, new_facts: dict, orders: list[dict]) -> dict` |
| `make_card_with_reply` | `l09` | `(ticket: Ticket, *, variant: str = "A", orders: list[dict] \| None \| "load" = "load", prompt: str = "zero", examples=None) -> CardResult`; `None` = сервіс замовлень не відповів; `prompt` міняє тільки запит картки |
| `search_kb` | `l10` | `(question: str, k: int = 3, mode: str = "hybrid") -> list[Chunk]` |
| `answer_from_kb` | `l10` | `(question: str) -> RagAnswer(found, answer, sources)` |

## 5. `call_model`: один виклик для всіх провайдерів

```python
# Це схема з support/llm/__init__.py
def call_model(messages: list[dict], *, system: str | None = None,
               schema: type | None = None, tools: list[dict] | None = None,
               model: str | None = None, effort: str = "low",
               max_output_tokens: int = 1024, timeout_s: float = 30.0,
               purpose: str = "card") -> ModelResult: ...

@dataclass
class ModelResult:
    status: Literal["ok", "tool_call", "refusal", "truncated", "error"]
    text: str = ""
    parsed: object | None = None    # pydantic-об'єкт, якщо schema= і перевірка пройшла
    tool_calls: list[ToolCall] = []
    usage: Usage = Usage()          # input_tokens (без кешу), output_tokens (з thinking), cached_input_tokens,
                                    # cache_write_tokens (частина input_tokens, записана в кеш; з 1.1)
    cost_usd: float = 0.0           # рахує НАШ код: usage x prices.py
    simulated_cost: bool = False    # True у mock
    latency_ms: int = 0
    provider: str = "mock"
    model: str = "mock-1"
    stop_reason: str = ""           # сире значення провайдера
    error: str | None = None        # "timeout", "rate_limit", "spend_cap", "schema_error", ...
    raw: dict | None = None
```

Правила:

- Провайдер: `AIEZ_PROVIDER` = `mock` (за замовчуванням) | `anthropic` | `openai` | `gemini` (живі з тегу `l06`). Модель: `AIEZ_MODEL`, інакше дефолт провайдера в `support/config.py`.
- Effort: `AIEZ_EFFORT` = `low` (за замовчуванням) | `medium` | `high`; `--effort` у `run_evals` його перекриває (тег `l07`). Усі три змінні є в `.env.example`.
- `call_model` не кидає винятків через провайдера: повертає `status="error"` і `error`. Виняток тільки на помилку програміста (порожній `messages`, невідомий `effort`).
- `schema=`: нативний structured output, де він є, і **завжди** локальна перевірка pydantic. Markdown-огорожі ```` ```json ```` знімаються перед перевіркою. Якщо текст не проходить схему: `status="ok"`, `parsed=None`, `error="schema_error"` (статус описує транспорт, `error` описує вміст).
- З тегу `l06`: один повтор тільки на `timeout` і `rate_limit`; кожен виклик пише один рядок у `runs/calls.jsonl` (без тексту звернення: тільки id, розміри, хеш, токени, ціна, час).
- `spend_cap` (вичерпаний бюджет чи ліміт витрат) ніколи не повторюється. Так адаптери мапують HTTP 402 і тексти `insufficient_quota`, `credit balance` / `credit_balance`, `billing`, `spend limit` / `spend_limit` (зокрема `enforced_spend_limit_reached`, `project_spend_limit_exceeded`), `spending cap`, `usage limits`, навіть коли провайдер повертає їх як 400 чи 429.
- Anthropic (тег `l06`): кожен запит має `cache_control: {"type": "ephemeral"}` (автоматичне кешування; запити, коротші за мінімум моделі, просто не кешуються), тож `cached_input_tokens` міряється. Вимкнути: `AIEZ_ANTHROPIC_CACHE=0`. Ключ без прив'язки до workspace потребує `ANTHROPIC_WORKSPACE_ID` у `.env`: адаптер шле його заголовком `anthropic-workspace-id`.
- Форма повідомлень: `{"role": "user" | "assistant", "content": str}`; виклик інструментів моделлю `{"role": "assistant", "content": "", "tool_calls": [{"id", "name", "args"}]}`; результат інструмента `{"role": "tool", "tool_call_id", "name", "content", "is_error"}`. Форма інструмента: `{"name", "description", "parameters": <JSON schema>}`. Адаптери перекладають це у формат провайдера.

**Mock-режим** (`support/llm/mock.py`), за замовчуванням: детермінований, без мережі, `cost_usd = 0.0` з `simulated_cost=True`, час фіксований (`120 мс + 1 мс на 10 вихідних токенів`), токени ≈ символи / 4. Картки беруться з `fixtures/mock_replies.jsonl` за `ticket_id`, інакше з невеликого fallback на правилах. Mock читає звернення з блоку `<ticket id="T-0001">текст</ticket>` в останньому повідомленні користувача.

Сценарії (`AIEZ_MOCK_SCENARIO`, `use_scenario(...)` або поле `"mock"` у рядку `cases.jsonl`): `ok`, `fenced_json`, `malformed_json`, `wrong_schema`, `invented_evidence`, `invented_category`, `refusal`, `truncated`, `rate_limit_then_ok`, `rate_limit`, `timeout`, `spend_cap`, `server_error`, `tool_call_status`, `tool_call_wrong_amount`, `tool_call_unoffered_tool`, `injection_followed`.

`prices.py` (тег `l06`): `{model: Price(input_per_mtok, output_per_mtok, cached_per_mtok, checked_at, url, cache_write_per_mtok=None)}`; `None` у записі в кеш означає 1,25 × ціна входу (5-хвилинний кеш Anthropic). `estimate_usd` рахує **один** запит: поріг довгого запиту (Haiku 5.5, 100K) діє на запит, ніколи на суму. Тільки звідти беруться ціни; дати й джерела в `docs/VERIFIED.md`. Модель без ціни: `cost_usd = 0.0`, а звіт `run_evals` пише `price unknown` і ніколи мовчки не вдає, що модель безкоштовна.

`uv run python -m support.llm --scenario <назва>` завжди йде через mock, навіть якщо `.env` каже живий провайдер (тег `l06`).

## 6. Інструменти (уроки 13–15; типи вже в `contract.py`)

Кожен інструмент першим аргументом бере `Ctx(customer_id, ticket_id, run_id)`. Модель `customer_id` не бачить і не заповнює. Очікувана помилка: `ToolError` (її текст може прочитати модель).

| Інструмент | Аргументи (strict pydantic, `extra="forbid"`) | Політика |
|---|---|---|
| `get_order_status` | `order_id` (`^DEMO-[0-9]{4}$`) | allow |
| `create_refund_draft` | `order_id`, `amount_kop: int > 0`, `reason` ∈ `не_прийшло`, `пошкоджено`, `не_той_товар`, `передумав` | allow; тільки `delivered`; `0 < amount ≤ total − refunded`; одна відкрита чернетка на замовлення |
| `search_kb` | `query` | allow |
| `issue_refund` | `draft_id` (`^RD-[0-9]{4}$`) | confirm |
| `send_reply` | `text` | confirm |

Усе, чого нема в таблиці: deny. `run_tool(ctx, name, args, *, allowed)` єдине місце виконання: відмовляє в іменах поза `allowed`, перевіряє аргументи строго (`"540"` не стає 540), повертає `(text_for_model, is_error)` і не пропускає `ToolError` нагору.

## 7. Цикл агента (урок 14)

`Limits(max_steps=5, max_seconds=60.0, max_cost_usd=0.05)`, `Step`, `AgentResult(status ∈ answered | handed_off | waiting_approval, text, reason, steps, cost_usd, run_id)`, `run_agent(ctx, message, *, tools, limits)`.

Кожен `ModelResult.status` має свою гілку: `ok` → відповідь; `tool_call` → `run_tool` для кожного виклику, усі результати одним повідомленням; `truncated`, `refusal`, `error` → передати людині з причиною в лозі. Маршрут: `classify_intent(ticket)` через `call_model(schema=Intent)` → `INTENT_TOOLS`.

## 8. Підтвердження і «рівно один раз» (уроки 15, 17)

- `action_id = new_action_id()`: випадковий `uuid4().hex[:12]`, ніколи не хеш аргументів. Хеш аргументів (`hash_args`) зберігається окремо, `UNIQUE(ticket_id, tool, args_hash)`. Нова пропозиція після `expired` створює нову дію; дія `done` ніколи не повертається в `waiting`.
- Аргументи `issue_refund` завжди містять `draft_id`.
- `can_approve(operator, action)`: роль і `operator != proposed_by`; інакше `{"status": "denied"}`.
- `execute_once`: атомарно `waiting → executing`; ключ ідемпотентності `idempotency_key(draft_id)` = `refund-RD-0001`; на винятку статус `failed` з помилкою, ніколи не застрягає в `executing`; на успіху повертає результат.

## 9. `evals/cases.jsonl` і `evals/own.jsonl`: один набір від уроку 1 до 20 плюс свої кейси

Один JSON-об'єкт на рядок, UTF-8, `ensure_ascii=False`. Поля: `id`, `added_in` (номер уроку), `kind`, `split` (`dev` | `holdout`), `tags`, `input`, `expect`, необов'язково `mock` (сценарій).

- `kind`: `card` (уроки 1–9), `retrieval` і `answer` (10), `tool` (13), `agent` (14), `policy` (15), `failure` (17).
- `input` для `card`: `ticket_id`, `customer_id`, `text`; з `l09` необов'язково `"orders": "not_loaded"` (сервіс замовлень не відповів). З `l09` модельний прогін `card` іде через `make_card_with_reply`, тож у результаті є `draft_reply`.
- `expect`: перелічені ключі мають збігтися точно, неперелічені не перевіряються. Ключі звіряються з полями `CardResult`. Оператори: `<поле>_in` (одне з), `must_contain`, `must_not_contain` (для `card` перевіряють `draft_reply`, для `answer` поле `answer`, для `agent` поле `text`), `tools_called`, `tools_not_called`, `no_action_over_kop`, `max_attempts`.
- id ідуть по порядку: `c001`–`c003` (урок 1, у `l03`), `c004`–`c030` (урок 5), `c031`–`c038` (урок 8, тег `contract`), `c039`–`c043` (урок 9, тег `context`).
- Жодних персональних даних.
- Кейс з полем `mock` перевіряє наш код на змодельованому збої, тому `run_evals` завжди проганяє його через mock, навіть у живому прогоні (тег `l07`). Живий звіт каже, скільки таких кейсів пішло через mock.

**Свої кейси учня: `evals/own.jsonl`** (файл є з тегу `l00`, порожній).

- Той самий формат рядка. id `own-01`, `own-02`, …, тож вони ніколи не збігаються з курсовими `cNNN`. Тег `own` (якщо забув, `run_evals` додає його сам).
- Для `card` можна не писати `ticket_id` і `customer_id`: тоді `T-OWN` і `c-17`. `kind` за замовчуванням `card`, `split` за замовчуванням `dev`. Категорія в `expect` поза списком контракту дає попередження.
- Додавай командою, без `>>`: `uv run python -m support.evals add-case "текст" --category доставка --order-id DEMO-1042` (тег `l03`). Вона бере наступний вільний `own-NN` і пише UTF-8.
- `evals/cases.jsonl` лишається еталонним набором курсу, свої кейси туди не пишеш. `run_evals` читає обидва файли (id не можуть повторюватись), `--tag own` запускає тільки свої.
- Тести стартера читають тільки `evals/cases.jsonl` і пропускають у ньому рядки з тегом `own`. Свої кейси ніколи не роблять `pytest` червоним, і скіл `pre-commit-check` через них коміт не зупиняє.
- Обидва файли в UTF-8. Якщо Windows PowerShell 5.1 дописав рядок через `>>` (UTF-16) або редактор поставив BOM, `run_evals` прочитає файл і попередить. Файл, який не читається, дає зрозуміле повідомлення українською, без traceback.
- Перенести свої кейси на гілку нового уроку: `git checkout lesson-<NN-1> -- evals/own.jsonl`; злити, нічого не перезаписуючи: `uv run python scripts/carry_own_cases.py lesson-<NN-1>`.

**Приклади для few-shot: `evals/examples.jsonl`** (тег `l09`).

- Рядок: `{"id": "e01", "text": "…", "card": {…}}`, де `card` це рівно та картка `TicketCard`, яку модель має повернути на цей текст. `--prompt one` бере перший рядок, `--prompt few` перші три, у порядку файлу.
- Приклад ніколи не береш з набору кейсів: тест `tests/test_prompting.py` падає, якщо текст прикладу з будь-якого `evals/examples*.jsonl` після нормалізації (регістр, пробіли, апострофи, розділові знаки) дорівнює входу кейсу з `cases.jsonl`. `run_evals` перед прогоном пише `WARNING`, якщо приклад збігся з кейсом з `cases.jsonl` чи `own.jsonl`.
- У стартері: `e01` доставка («Курʼєр двічі переносив доставку…»), `e02` невідомо («Ну і що тепер?», цитата `null`), `e03` інше (подяка, не `c011`). `evals/examples_bias.jsonl`: три приклади `обмін` для вправи на упередження.

**Покриття і точність** рахуються тільки на кейсах, де `expect.category` задана й не `null`: покриття = скільки з них отримали категорію (не «не знаю»), точність = скільки з отриманих правильні. `"category": null` в `expect` означає «код не має вирішувати» (напр. категорія без доказу) і в покриття не входить.

## 10. `run_evals`

```text
uv run python -m support.evals [--kind card] [--baseline] [--provider mock] [--model ID]
    [--effort low] [--variant A] [--prompt zero] [--examples FILE] [--reverse-examples]
    [--runs 1] [--vote] [--split dev] [--tag edge] [--id c039]
    [--dry-run] [--max-usd 0.05] [--label NAME]
uv run python -m support.evals add-case "текст" [--category C] [--order-id DEMO-1042] [--amount-kop N]
    [--status ok] [--must-contain TEXT] [--tag T] [--customer c-17] [--mock SCENARIO]
```

Прапорці з'являються разом з уроками: `--baseline`, `--tag`, `--split`, `--label`, `--id` і `add-case` у `l03`; `--provider`, `--model`, `--effort`, `--runs`, `--dry-run`, `--max-usd` у `l07`; `--variant`, `--prompt`, `--examples`, `--reverse-examples`, `--vote` у `l09`.

- `--tag own` бере тільки свої кейси з `evals/own.jsonl`. `--id` можна повторити: `--id c039 --id c041` проганяє тільки ці кейси.

- `--baseline`: правила (`make_card_rules`, `triage_rules`) замість моделі. Час правил не міряється.
- `--prompt zero|one|few|reason` (тег `l09`): техніка промпта, окремо від `--variant` (варіант = як розкладені частини, техніка = що додано). `zero` за замовчуванням, вивід як до 1.2. `one` / `few`: 1 / 3 перші приклади з `--examples FILE` (за замовчуванням `evals/examples.jsonl`); `--reverse-examples` ставить ті самі приклади у зворотному порядку. `reason`: коротке пояснення `why` перед відповіддю (`TicketCardReasoned`). Заголовок звіту: `· prompt few (e01, e02, e03)`; у mock після FAIL-рядків стоїть `note: on mock the prompt effect is a fixed teaching rule (CONTRACT.md 11.14); a live run measures the real one`. Мітка `runs/` отримує `-few`, `-<файл прикладів>` (якщо `--examples`), `-rev`, `-vote`.
- `--runs N --vote` (тег `l09`): N прогонів кожного кейсу стають одним результатом за більшістю категорії (більше половини голосів). Нема більшості: `status="needs_review"`, `category=None`, `checks["vote"] = "reject: голоси розійшлись (…)"`. Ціна й час = сума N прогонів, `--dry-run` уже множить на N. Заголовок: `× 3 runs · vote`. Mock детермінований, тож у mock голоси завжди сходяться; різницю дає живий прогін.
- `--model` можна повторити (`--model mock:mock-1 --model anthropic:claude-haiku-5-5`), тоді в кінці таблиця порівняння (тег `l07`).
- `--dry-run`: кількість викликів і оцінка ціни з `prices.py` до будь-яких витрат (тег `l07`). Ціна рахується на один виклик і множиться на кількість викликів; з `l09` враховує `--variant` і `--prompt` (приклади додають вхідні токени).
- `--max-usd 0.05`: стоп бюджету. Перед кожним наступним кейсом прогін перевіряє, скільки вже витрачено, і зупиняється, коли досяг ліміту (може перебрати на один кейс). Звіт рахує тільки виконані кейси й пише `budget stop: $X of $Y spent · N of M cases not run` (тег `l07`).
- Пише `runs/<YYYYMMDD-HHMMSS>-<label>.json` з кожним результатом. Мітка: `baseline` для `--baseline` (або `--label NAME`); для моделі `[NAME-]<provider>-<model>-<effort>`, з `l09` плюс `-B`, якщо варіант не `A`. Два прогони за одну хвилину й кілька `--model` з одним `--label` більше не пишуть в один файл.
- `--min-pass` (поріг і код виходу 1 для CI) з'являється в тезі `l11`.

Формат виводу (тест фіксує його):

```text
run 20261102-101233 · kind=card · provider=mock model=mock-1 · cases 30 (dev)
pass 26/30 (86.7%) · coverage 28/30 · precision 26/28
cost $0.0000 (simulated) · per case $0.0000 · per success $0.0000
latency p50 140 ms · p95 180 ms
FAIL c007 [edge] category: expected невідомо, got інше
```

Модельний прогін додає після `latency` рядок `tokens in N · out M · cached K` і, якщо були збої провайдера, `errors N/M (first: ...)`; якщо ціни моделі нема в `prices.py`, рядок `price unknown for <model>: cost shown as $0, add it to support/prices.py`. `--baseline` пише `cost $0.0000 (rules)` і `latency n/a (rules, not measured)`. Утримання правил у рядку FAIL показується як `got не знаю`. Перший тег кейсу стоїть у дужках.

## 11. Рішення, які варто знати (версії 1.0–1.2)

1. Тег `lNN` це стан **у кінці** уроку NN (еталон). `git diff l07 l08` показує рівно те, що додає урок 8. Учень працює в одній гілці на урок, `lesson-NN`. Урок 0 стартує з `l00`; уроки 1–4, де учень будує сам, з `l(NN-1)`; з уроку 5 урок стартує з власного тегу `lNN` (учень читає, запускає, ламає й розширює готовий код). Свої кейси переносить `git checkout lesson-<NN-1> -- evals/own.jsonl` (розділ 9).
2. `CardResult.category` додано до контракту: таблиця версій каже «+ category від правил», а поля в схемі не було.
3. Відповідь, що не пройшла схему, це `status="ok"` + `error="schema_error"` + `parsed=None` у `ModelResult`, і `status="schema_error"` у `CardResult`. `make_card` повторює виклик один раз тільки на `schema_error`; відмову й обрізаний вихід не повторює.
4. Перший `make_card` з'являється в `l06` (без перевірок доказів), щоб уроки 6 і 7 мали модельний шлях; урок 8 додає перевірки.
5. Категорія без доказу або з вигаданою цитатою: `checks["category"] = "reject: ..."`, `CardResult.category = None`, статус `needs_review`. Вигадана категорія ніколи не стає категорією картки.
6. Якщо у зверненні кілька номерів замовлень, береться перший.
7. `Usage.input_tokens` це некешований вхід; кешований іде в `cached_input_tokens`. Адаптери віднімають кеш там, де провайдер рахує його всередині `input_tokens`.
8. id кейсів ідуть по порядку файлу, тому приклад `c021` з плану курсу (ін'єкція в уроці 8) у репозиторії має інший номер: ін'єкція T-0010 це `c010` (урок 5) і `c043` (урок 9), а сценарій `invented_category` це `c032` з очікуванням `needs_review` і `category: null`.
9. Звернення `data/tickets.jsonl` (30 штук) є з тегу `l00`, бо демо уроку 0 показує картку; розмітка категорій з'являється в `l05`. Для швидкої перемоги уроку 5 є тег кейсів `demo` (10 кейсів): `uv run python -m support.evals --baseline --tag demo` → `coverage 4/10 · precision 3/4`.
10. Варіант `B` (урок 9) відрізняється від `A` одним рішенням: частини запиту в тегах, правила першими, а блок замовлень каже `status="not_loaded"` замість порожнього. `must_contain` / `must_not_contain` для `card` перевіряють `draft_reply`.
11. `customer_id` у `POST /api/card` не приймається (422): сервер бере його з сесії (`DEMO_SESSION_CUSTOMER = "c-17"`).
12. `make_card_with_reply` (тег `l09`) перевіряє власника замовлення. Якщо сервіс замовлень відповів, а номера нема серед замовлень цього клієнта: `checks["order_id"] = "reject: не замовлення цього клієнта"`, `order_id=None`, статус `needs_review`. Чуже й неіснуюче виглядають однаково. Чернетка каже «Не бачу замовлення … серед ваших», бо в запит іде тільки цей клієнт. Якщо сервіс не відповів (`orders=None`), власника не перевірити: номер лишається, чернетка каже, що дані не завантажились. Сам `make_card` замовлень не читає й власника не перевіряє. Змішування фактів різних звернень у стані клієнта (сума від одного замовлення при іншому номері) лишається навмисною вправою уроку 9 і виправляється в `l10`.
13. Сервіс (`support/server.py`, тег `l03`) дозволяє CORS тільки для локальних dev-адрес `http://localhost:<порт>` і `http://127.0.0.1:<порт>` (Vite на 5173 тощо), методи GET і POST, без cookies. Іншим джерелам браузер відмовить.

14. **Mock реагує на промпт картки** (тег `l09`, `support/llm/mock.py`). Це навчальна імітація типової поведінки, не модель: справжній ефект міряє живий прогін. Правила чіпають тільки «неоднозначну» відповідь mock, тобто категорію `інше` або `невідомо`; ясну відповідь (`брак` з цитатою «розбитий») приклади не міняють.
    1. **Збіг з прикладом.** Приклад «схожий» на звернення, якщо слово з його `category_evidence` і слово звернення мають однаковий початок (перші 5 літер слова з 4+ літер, апострофи зведені). Приклад з `category_evidence: null` схожий на звернення, для якого mock теж не має цитати. Категорія стає категорією прикладу, цитата = слово звернення (або `null`). Якщо схожих прикладів кілька, перемагає **останній** у запиті: порядок прикладів має значення.
    2. **Упередження.** Жоден приклад не схожий, а три останні приклади мають одну категорію: відповідь тягнеться до неї, цитата = перше слово звернення. Цитата справжня, тому перевірка доказу її пропускає, а категорія хибна.
    3. **Поле `why`.** Якщо схема має `why` (`TicketCardReasoned`), mock пише його першим і для ще неоднозначної відповіді перечитує таблицю категорій (розділ 2, колонка «Коли»): слово звернення з неї (кур'єр, посилка, розмір, колір, пароль…) дає категорію.

    Що це дає на 43 кейсах (варіант `A`, mock): `zero` 39/43 (провали c011, c021, c025, c039), `one` 40/43 (`e01` «Курʼєр…» лагодить c021), `few` 42/43 (`e03` подяка лагодить c011, `e02` «невідомо» лагодить c025), `reason` 40/43 (кур'єр = доставка лагодить c021). Ті самі три приклади у зворотному порядку: 41/43, c011 знову `невідомо` (останнім схожим став `e02`). `evals/examples_bias.jsonl` (три `обмін`): 37/43, c011, c019, c021, c025, c026 стають `обмін`. c039 падає тільки у варіанті `A` (розділ 11.10).

## 12. Зміни у версії 1.1 (24.10.2026)

Кожна зміна стоїть на найранішому тезі, якого вона стосується. Історію тегів `l00`…`l09` перебудовано, тож `lNN` і далі означає кінець уроку NN.

| Тег | Зміна |
|---|---|
| `l00` | `evals/own.jsonl` (порожній) і правило своїх кейсів: id `own-NN`, тег `own`, `run_evals` читає `cases.jsonl` + `own.jsonl`, тести тільки `cases.jsonl` (розділ 9) |
| `l00` | Правило гілок: одна гілка на урок `lesson-NN`, стартовий тег за розділом 11.1; README описує його й блок команд на початку уроку |
| `l00` | `scripts/carry_own_cases.py <гілка>`: дописує свої кейси з іншої гілки без перезапису; нема файлу чи гілки, нічого не робить |
| `l00` | `.gitignore`: `try_*.py` (блоки Python з уроків) |
| `l00` | `scripts/doctor.py`: Python 3.13+ і відсутній uv дають `WARN`, не `FAIL` (pip-шлях) |
| `l00` | `support.demo`: порожні теги друкуються як `нема` замість тире |
| `l00`…`l09` | `requirements.txt` (`uv export`) на кожному тезі для pip-шляху; тест звіряє його з `uv.lock` |
| `l00` | `AGENTS.md` = `CLAUDE.md`: свої кейси живуть в `own.jsonl`, їхні FAIL коміт не блокують; файли `try_*.py` |
| `l00` | `AIEZ_EFFORT` описано в розділі 5 |
| `l01` | `web/index.html`: номер це рівно 4 цифри (`(?!\d)`), `DEMO-10420` не номер, як у `rules.py` |
| `l01` | `tests/test_prototype.py`: `KB.md` перевіряється тільки на розділ «Перевірки», тож свій `KB.md` у будь-якому форматі не робить тести червоними |
| `l02` | Скіл `pre-commit-check` (обидві копії): «Сам нічого не коміть», тригер «закоміть», свої кейси не зупиняють коміт |
| `l03` | `run_evals`: читає `own.jsonl`, `--tag own`, `--id`, `add-case`; читає UTF-16/BOM з попередженням; нечитабельний файл дає повідомлення українською без traceback |
| `l03` | Імена файлів `runs/`: секунди в `run_id` (`YYYYMMDD-HHMMSS`) |
| `l03` | Рядок `latency n/a (rules, not measured)` без тире |
| `l03` | CORS для `localhost` / `127.0.0.1` на будь-якому порту (розділ 11.13) |
| `l04` | `specs/repeat-tickets.md`: речення «скільки разів про це саме замовлення вже писали», крок 3 «віком від 10 хв до 30×24 год, обидві межі включно», критерій 1 «Коли рахую повторні для DEMO-1042» |
| `l06` | `spend_cap` упізнається за 402 і сучасними текстами помилок, без повтору (розділ 5) |
| `l06` | Anthropic: `cache_control` на кожному запиті, `AIEZ_ANTHROPIC_CACHE=0` вимикає; необов'язковий `ANTHROPIC_WORKSPACE_ID` → заголовок `anthropic-workspace-id`; обидва в `.env.example` |
| `l06` | `Usage.cache_write_tokens`, `Price.cache_write_per_mtok`: запис у кеш Anthropic коштує 1,25 × вхід, а не як звичайний вхід |
| `l06` | `support.llm --scenario` завжди йде через mock |
| `l06` | `docs/VERIFIED.md`: Gemini generateContent (legacy, повністю підтримується), вимога workspace в Anthropic, форми помилок ліміту витрат |
| `l07` | `--dry-run` рахує ціну на один виклик × кількість викликів (поріг 100K більше не спрацьовує на сумі) |
| `l07` | `--max-usd` (стоп бюджету) |
| `l07` | Імена `runs/` з provider, model і effort; `--label` з кількома `--model` більше не пише в один файл |
| `l07` | Кейси з полем `mock` у живому прогоні йдуть через mock |
| `l07` | Звіт пише `price unknown for <model>`, коли моделі нема в `prices.py` |
| `l07` | `.env.example`: `AIEZ_EFFORT=low` |
| `l09` | `make_card_with_reply`: перевірка власника замовлення (розділ 11.12); кейс `c041` чекає `needs_review` і `order_id: null` |
| `l09` | `--dry-run` враховує `--variant` |

## 13. Зміни у версії 1.2 (24.10.2026)

Усе в тезі `l09`, бо техніки промптів учить урок 9; теги `l00`–`l08` не змінились і лишаються на 1.1. Вивід без нових прапорців той самий, що в 1.1.

| Тег | Зміна |
|---|---|
| `l09` | `run_evals --prompt zero\|one\|few\|reason`, окремо від `--variant`; `zero` за замовчуванням = запит 1.1 без змін (розділ 10) |
| `l09` | `build_card_prompt`, `make_card`, `make_card_with_reply` приймають `prompt=` і `examples=`; приклади йдуть блоком `<examples>` прямо перед `<ticket>` |
| `l09` | `evals/examples.jsonl` (3 підписані демо-звернення `e01`–`e03`) і `evals/examples_bias.jsonl` (3 × `обмін`); `load_examples`; `--examples FILE`, `--reverse-examples` |
| `l09` | Тест: жоден приклад не дорівнює входу кейсу після нормалізації; `run_evals` попереджає про такий приклад і для `own.jsonl` |
| `l09` | `TicketCardReasoned`: необов'язкове коротке `why` першим полем (до 300 знаків, код обрізає); `make_card` відкидає його до перевірок, у `CardResult`, UI й API його нема |
| `l09` | Mock реагує на приклади й поле `why` за трьома правилами (розділ 11.14); звіт у mock з `--prompt` пише рядок `note: …` |
| `l09` | `--runs N --vote`: більшість категорії, без більшості `needs_review` (розділ 10) |
| `l09` | `CONTRACT_VERSION = "1.2"` |
| `l09` | Поле `reasoning` перейменоване на `why` (24.10.2026): документація Anthropic про відмови називає поле `reasoning` у JSON типовою причиною оплачуваної відмови `reasoning_extraction` і дозволяє коротке пояснення (https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#keep-reasoning-in-thinking-blocks). Версія лишається 1.2 |
