# Стартовий проєкт курсу «AI Engineering з нуля»

Робочий проєкт, на якому працює код кожного уроку: інструмент оператора підтримки для вигаданого магазину «Демо-маркет». Звернення клієнта → картка → AI-картка з перевіркою доказів → відповідь → агент із підтвердженням людини.

- Усе працює **без ключа і без мережі**: mock-режим за замовчуванням, ціна $0.
- Один контракт імен і даних на весь курс: [CONTRACT.md](CONTRACT.md).
- Кожен урок має свій git-тег `l00`, `l01`, …: стан проєкту в кінці уроку.
- Одна гілка на урок, `lesson-NN`, і свої кейси в `evals/own.jsonl`: розділ [Гілки і свої кейси](#гілки-і-свої-кейси).

## Запуск за 10 хвилин (Windows, PowerShell)

**1. Git і uv.** Відкрий Windows Terminal (PowerShell) і виконай:

```powershell
winget install --id Git.Git -e
winget install --id=astral-sh.uv -e
```

Якщо `winget` заблокований: офіційний PowerShell-інсталятор uv з [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/). Після встановлення **закрий і відкрий термінал заново**.

**2. UTF-8 для Python.** Один раз, потім знову новий термінал. Без цього український `print` може впасти з `UnicodeEncodeError: 'charmap'`, коли скрипт запускає асистент.

```powershell
setx PYTHONUTF8 1
```

**3. Клонуй у коротку папку** без пробілів і кирилиці, не в OneDrive. Саме `git clone`, не zip: «Видобути все» кладе файли на рівень глибше, і асистент не бачить `AGENTS.md`.

```powershell
mkdir C:\dev
cd C:\dev
git clone <адреса-репозиторію> ai-engineering-starter
cd ai-engineering-starter
git switch -c lesson-00 l00
```

**4. Python 3.12 і залежності.** uv сам ставить потрібний Python, без Microsoft Store і без галочки PATH. Перший `uv sync` може йти довго через перевірку Defender.

```powershell
uv python install 3.12
uv sync
```

Корпоративний ноутбук, де uv поставити не можна? Pip-шлях: Python 3.12 або новіший з python.org, потім у папці стартера:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

`requirements.txt` лежить на кожному тезі й збігається з `uv.lock` цього тегу. Далі замість `uv run python` пиши `.venv\Scripts\python`, замість `uv run pytest` пиши `.venv\Scripts\python -m pytest`. Після кожного `git switch` на новий тег повтори `pip install -r requirements.txt`. `doctor.py` на цьому шляху покаже `WARN` на рядку uv (і на Python 3.13+), це нормально.

**5. Перевір середовище.** Усі рядки мають бути `OK`. `--save` записує `doctor.txt`, щоб показати результат.

```powershell
uv run python scripts/doctor.py --save
```

**6. Перша картка звернення, без ключа:**

<!-- run: l00+ -->
```powershell
uv run python -m support.demo
```

```output
Демо-маркет · картка звернення
Звернення T-0001 (c-17): Не отримав посилку, замовлення DEMO-1042
категорія:  доставка  ← «посилку»
замовлення: DEMO-1042  ← «DEMO-1042»
сума:       невідомо
теги:       нема
status=ok · provider=mock model=mock-1 · tokens 49→44 · cost $0.0000 (simulated) · 124 ms
```

**7. Тести:**

```powershell
uv run pytest -q
```

Останній рядок має бути `N passed` без `failed`. Скільки тестів на якому тезі: [docs/TAGS.md](docs/TAGS.md) (з тегу `l09`).

## Чому `uv run`, а не `python`

`uv run` бере Python 3.12 і залежності саме цього проєкту без активації середовища, тож політика виконання скриптів PowerShell його не блокує. Голий `python` на Windows може відкрити Microsoft Store або взяти іншу версію. Ті самі команди працюють на macOS і Linux.

## Гілки і свої кейси

Тут дві папки. Стартер це лабораторія, де запускається код кожного уроку. Свій проєкт (`my-first-product` або твоя апка) живе в окремій папці, туди переносиш кожен урок у блоці «У твоєму проєкті».

- **Тег `lNN`** це еталон кінця уроку NN. Його не змінюєш.
- **Одна гілка на урок:** `lesson-NN`. Інших назв нема.
- **Звідки стартує урок:** урок 0 з `l00`. Уроки 1–4, де будуєш сам, з тегу попереднього уроку `l(NN-1)`. З уроку 5 урок стартує з власного тегу `lNN`, а що він додав, показує `git diff l(NN-1) lNN`. Точний тег кожного уроку стоїть у блоці «Код уроку».
- **Той самий блок на початку кожного уроку**, змінюються тільки номери (приклад для уроку 6):

```powershell
git switch -c lesson-06 l06
git checkout lesson-05 -- evals/own.jsonl
uv sync
```

Якщо друга команда каже, що файлу нема, своїх кейсів ще нема, це нормально. Незакомічені нотатки в `STATE.md` заважають `git switch`: спершу `git add -A` і `git commit -m "кінець уроку NN"`.

**Свої кейси** живуть тільки в `evals/own.jsonl`: id `own-01`, `own-02`, …, тег `own`. `evals/cases.jsonl` це еталонний набір курсу, теги його змінюють, тому туди свого не дописуй. `run_evals` читає обидва файли, `--tag own` запускає тільки твої. Тести стартера читають тільки `cases.jsonl`, тож свої кейси їх не ламають.

Новий кейс додавай командою (з уроку 3), не через `>>`: у Windows PowerShell 5.1 `>>` пише UTF-16.

```powershell
uv run python -m support.evals add-case "Де моя посилка? DEMO-1042" --category доставка --order-id DEMO-1042
```

Хочеш злити свої кейси з іншої гілки, нічого не перезаписуючи: `uv run python scripts/carry_own_cases.py lesson-05` (додає тільки рядки з новими id).

**Блоки Python з уроків** зберігай як `try_<назва>.py` у корені стартера, запускай `uv run python try_<назва>.py` і видаляй. `try_*.py` є в `.gitignore`.

## Теги

| Тег | Що додає |
|---|---|
| `l00` | каркас, контракт, mock `call_model`, `doctor.py`, демо, snippet-тести, порожній `evals/own.jsonl`, `requirements.txt` |
| `l01` | прототип у браузері `web/index.html`, 3 перевірки в `KB.md` |
| `l02` | скіл `pre-commit-check` для асистента |
| `l03` | `support/rules.py`, FastAPI-сервіс, тести, перші 3 кейси, `run_evals --baseline` |
| `l04` | SQLite `tickets`, `count_repeats`, специфікація й тести повторних звернень |
| `l05` | `triage_rules`, 30 розмічених кейсів, `support.tokens` |
| `l06` | живі адаптери OpenAI / Anthropic / Gemini, `prices.py`, `runs/calls.jsonl`, перший `make_card` |
| `l07` | `run_evals` на кількох моделях, `--dry-run`, шаблон `model-choice.md` |
| `l08` | перевірка доказів у `make_card`, гроші в копійках, 8 крайніх кейсів |
| `l09` | контекст: стан клієнта, чернетка відповіді, варіанти A/B; техніки промпта: 0, 1, 3 приклади, коротке пояснення `why` (`--prompt`) |

Відстав або заплутався? Почни урок з його тегу за блоком вище, свої кейси перенесе друга команда.

## Корисні команди

```text
uv sync                                   # один раз на тег
uv run pytest -q                          # тести, без мережі й ключів
uv run python -m support.demo T-0007      # картка будь-якого звернення
uv run python scripts/doctor.py           # перевірка середовища
```

## Живий API (з уроку 6)

Скопіюй `.env.example` у `.env` (він у `.gitignore`, у git не потрапляє), впиши `AIEZ_PROVIDER` і ключ свого провайдера. Ключ живе тільки на сервері й у `.env`, ніколи в `web/` чи в коді. Постав ліміт витрат у кабінеті провайдера до першого виклику.

## Для авторів уроків

- Правила для асистента: [AGENTS.md](AGENTS.md) (те саме в `CLAUDE.md`).
- Як позначати код уроку, щоб тест перевіряв «запускається як надруковано»: [docs/SNIPPETS.md](docs/SNIPPETS.md).

Ліцензія MIT, © Anton Shumeiko.
