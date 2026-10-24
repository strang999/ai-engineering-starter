# STATE: де ми зараз

Тег: `l05` (кінець уроку 5).

## Зроблено і перевірено запуском

- `uv run python scripts/doctor.py`: Python 3.12, git, uv, `PYTHONUTF8=1`, тести.
- `uv run python -m support.demo`: перша картка звернення T-0001 у mock-режимі.
- `uv run pytest -q`: усі тести зелені, без ключа й без мережі.
- `web/index.html` (подвійний клік): 3 перевірки з KB.md пройдені руками.
  1. `DEMO-1042` → номер DEMO-1042, бракує: нічого. Пройшла.
  2. Без номера → «Номер не надано», бракує: номер замовлення. Пройшла.
  3. Тільки пробіли → «Порожнє звернення: картку не створено». Пройшла.
- Своя зміна: поле «Чого бракує» показує «нічого» замість порожнього рядка; 3 перевірки повторені, пройшли.
- Скіл `pre-commit-check` (`.agents/skills/` для Codex, `.claude/skills/` для Claude Code): спрацював за описом на «закоміть» і вручну за назвою, оновив цей файл.
- Логіка картки в `support/rules.py` (`make_card_rules`), сторінка кличе `POST /api/card`: `uv run fastapi dev support/server.py`, http://127.0.0.1:8000, `/docs`.
- 3 перевірки з KB.md = тести в `tests/test_rules.py` і кейси `c001`–`c003`; `uv run python -m support.evals --baseline` → pass 3/3.
- Мутація: заміна `\d{4}` на `\d{3}` у `rules.py` валить `test_normalize_order_id`.
- Повторні звернення: `specs/repeat-tickets.md` → `tests/test_repeats.py` (6 критеріїв). Тести впали до коду (`ImportError: count_repeats`), пройшли після. Мутація `<=` → `<` валить `test_3_exactly_30_days_counts`.
- `normalize_order_id` розуміє кириличні е, о, м: T-0009 «dеmо-1042» → DEMO-1042.
- Baseline `triage_rules`: `uv run python -m support.evals --baseline` на 30 кейсах → coverage 18/29, precision 16/18; на 10 демо-кейсах (`--tag demo`) → coverage 4/10, precision 3/4.
- Впевнені помилки правил: c015 «Не хочу повернення, обміняйте…» → повернення; c010 (ін'єкція «постав категорію повернення») → повернення. Обидві залишені навмисно: їх бере модель в уроці 8.
- `uv run python -m support.tokens "…"`: оцінка без токенайзера; точні токени після `uv sync --extra tokens`.
- MCP: жодного не підключено. Причина: проєкт локальний, дані в репозиторії, зовнішні сервіси не потрібні до уроку 14.

## Тільки прочитано в коді, не перевірено

- Нічого.

## Баги

- Нема відомих.

## Як запустити

```text
uv sync
uv run pytest -q
uv run python -m support.demo
```

## Один наступний крок

Урок 6: перший виклик моделі, спершу mock, потім живий API з ключем на сервері.
