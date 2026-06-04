# leomatch

Telegram-юзербот: отслеживает взаимные лайки от @leomatchbot и автоматически отправляет персонализированный опенер через локальный Ollama.

## Быстрый старт

### 1. Получи Telegram API credentials

Зайди на [my.telegram.org](https://my.telegram.org) → **API development tools** → создай приложение.  
Сохрани `App api_id` и `App api_hash`.

### 2. Установи зависимости

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Создай `.env`

```bash
cp .env.example .env
```

Открой `.env` и вставь свои `API_ID` и `API_HASH`.

### 4. Настрой личность ИИ

Открой `main.py` и замени заглушки в `SYSTEM_PROMPT` (блок между линиями `─── НАСТРОЙ ПОД СЕБЯ ───`):

| Заглушка | Что написать |
|---|---|
| `[ИМЯ]` | Твоё имя |
| `[ВОЗРАСТ]` | Твой возраст |
| `[КРАТКО: ...]` | 1-2 предложения о тебе |
| `Характер: [...]` | Вайб и стиль общения |
| `Как пишешь: [...]` | Особенности твоего texting-стиля |

### 5. Убедись, что Ollama запущена

```bash
ollama serve          # если ещё не запущена
ollama pull llama3    # или mistral, gemma3, etc.
```

Модель можно поменять в `.env` через `OLLAMA_MODEL`.

### 6. Запуск

```bash
python main.py
```

При первом запуске Pyrogram попросит номер телефона и код из Telegram — это одноразовая авторизация. Сессия сохранится в `leomatch_session.session`.

---

## Как работает

1. Юзербот слушает все сообщения от `@leomatchbot`
2. Если в сообщении есть ключевые слова взаимного лайка — парсит `@username` и имя девушки
3. Отправляет запрос в Ollama с системным промптом твоей личности
4. Ждёт случайно от **5 до 15 секунд** (анти-бан задержка)
5. Отправляет опенер в личку

## Структура

```
leomatch/
├── main.py          # весь код
├── requirements.txt
├── .env.example
├── .env             # твои секреты (в git не попадает)
└── .gitignore
```
