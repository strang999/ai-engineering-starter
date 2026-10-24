# STATE: де ми зараз

Тег: `l00` (кінець уроку 0).

## Зроблено і перевірено запуском

- `uv run python scripts/doctor.py`: Python 3.12, git, uv, `PYTHONUTF8=1`, тести.
- `uv run python -m support.demo`: перша картка звернення T-0001 у mock-режимі.
- `uv run pytest -q`: усі тести зелені, без ключа й без мережі.

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

Урок 1: обрати свою таску й написати 3 перевірки до коду.
