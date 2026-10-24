# STATE: де ми зараз

Тег: `l04` (кінець уроку 4).

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

Урок 5: baseline на правилах, покриття й точність на 30 кейсах.
