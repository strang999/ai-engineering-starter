# Snippet convention for lesson writers

Every code block in a code lesson either **runs as printed** against a starter tag, or is labelled «Це схема, не готовий код». The harness `scripts/check_snippets.py` (also run by `tests/test_snippets.py`) proves the first kind.

## The marker

Put an HTML comment on the line right before the opening fence:

| Marker | Runs at |
|---|---|
| `<!-- run: l05 -->` | tag `l05` only |
| `<!-- run: l05+ -->` | tag `l05` and every later tag (use it for output that must stay stable, e.g. the demo) |

The comment is invisible on the site and in Telegram-rendered Markdown. Which tag to use: the state the learner has **when they type the block**. Tag `lNN` is the end of lesson NN, so a block in the middle of lesson 8 that uses `make_card` must run against `l08` (the lesson's reference state). Blocks a learner writes themselves (exercises) are not marked; their solution ships in the tag.

## What can run

- ` ```python ` blocks: saved to a temp file and run with the tag's Python from the repo root (`support` is importable). Each block must be **self-contained**: its own imports, no names from earlier blocks.
- ` ```powershell ` (or `shell`, `text`, `console`) blocks: every non-empty line must be `uv run python ...` or `uv run pytest ...`. Lines starting with `#` are skipped; a leading `PS>` prompt is allowed. Other commands (`git`, `winget`, `setx`, `cd`) cannot be checked, so leave those blocks unmarked.

The harness runs everything with `PYTHONUTF8=1`, `AIEZ_PROVIDER=mock`, no `.env`, no network. Anything that needs a live key is not marked; show its expected output as an example and say so («приклад з живого API, цифри в тебе будуть інші»).

## Expected output

The fenced block **right after** the code block, with the info string `output`, is the expected stdout. Comparison ignores trailing spaces and trailing blank lines. Two wildcards:

- a line that is exactly `...` matches any number of lines;
- `{*}` inside a line matches any text (timestamps, run ids, paths).

No `output` block means: the block only has to exit with code 0.

## Examples (these run in the repo's own tests)

<!-- run: l00+ -->
```python
from support.contract import format_kop

print(format_kop(125000))
print(format_kop(54000))
```

```output
1 250,00 грн
540,00 грн
```

<!-- run: l00+ -->
```powershell
uv run python -m support.demo T-0007
```

```output
Демо-маркет · картка звернення
Звернення T-0007 (c-17): Списали 1 250,00 грн двічі, помилка E-217
...
status=ok · provider=mock model=mock-1 · {*} · cost $0.0000 (simulated) · {*} ms
```

## Checking a lesson

```text
git switch --detach l05
uv sync
$env:AIEZ_LESSONS_DIR = "C:\path\to\lessons"
uv run pytest tests/test_snippets.py -q
uv run python scripts/check_snippets.py "C:\path\to\lessons\Lesson 05.md"
```

The second command prints PASS/FAIL per block with the expected and actual output side by side. `AIEZ_LESSONS_DIR` takes a folder (all `*.md` inside) or a file; separate several with `;` on Windows.
