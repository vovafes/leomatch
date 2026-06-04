import re
import yaml
from pathlib import Path
from openai import AsyncOpenAI
import config

PERSONA_FILE = Path(__file__).parent.parent / "persona.yml"

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL or None,
        )
    return _client


def load_persona() -> dict:
    with open(PERSONA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_persona(data: dict):
    fields = ["name", "age", "about", "character", "writing_style", "taboo"]
    clean = {k: data[k] for k in fields if k in data}
    # age must be int
    if "age" in clean:
        clean["age"] = int(clean["age"])
    with open(PERSONA_FILE, "w", encoding="utf-8") as f:
        yaml.dump(clean, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def build_system_prompt(persona: dict, mode: str = "chat") -> str:
    if mode == "opener":
        task = (
            "написать ОПЕНЕР — одно первое сообщение (1–2 предложения максимум) "
            "девушке, с которой у тебя взаимный лайк в приложении знакомств Дайвинчик."
        )
        rules = (
            "• Сообщение живое и нативное — никто не должен догадаться, что это бот\n"
            "• Никакого «Привет, как дела?» или шаблонного флирта\n"
            "• Лёгкий юмор, подкол или интригующий вопрос — приветствуется\n"
            "• Если известно имя — используй органично, не в самом начале\n"
        )
    elif mode == "nudge":
        task = (
            "написать ОДНО очень короткое сообщение девушке, которая давно не отвечала. "
            "Как будто тебе стало интересно, куда она пропала — без претензий, легко."
        )
        rules = (
            "• Максимум одно предложение, очень коротко\n"
            "• Никакого нытья и «почему не отвечаешь»\n"
        )
    else:
        task = (
            "поддерживать живой диалог с девушкой из приложения знакомств Дайвинчик. "
            "Ты уже написал ей первым, она ответила — продолжай общение."
        )
        rules = (
            "• Читай контекст и отвечай по смыслу, не повторяй сказанное\n"
            "• Задавай вопросы и проявляй интерес, но не заваливай ими\n"
            "• Отвечай коротко (1–3 предложения), если её сообщение тоже короткое\n"
            "• Если разговор идёт хорошо и уместно — можно намекнуть на встречу\n"
        )

    return (
        f"Ты — {persona['name']}, {persona['age']} лет. {str(persona['about']).strip()}.\n\n"
        f"Характер: {str(persona['character']).strip()}.\n"
        f"Как пишешь: {str(persona['writing_style']).strip()}.\n"
        f"Табу: {str(persona['taboo']).strip()}.\n\n"
        f"Задача: {task}\n\n"
        f"Правила:\n"
        f"• Пиши живо и нативно — никто не должен догадаться, что это ИИ\n"
        f"• Веди себя как ты, не как бот и не как пикап-гуру\n"
        f"{rules}"
        f"• Отвечай ТОЛЬКО текстом сообщения — без кавычек и пояснений"
    )


def is_spam(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in config.SPAM_KEYWORDS)


def is_suspicious(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in config.SUSPICIOUS_PATTERNS)


async def generate_message(
    history: list[dict],
    user_prompt: str | None = None,
    mode: str = "chat",
) -> str:
    persona = load_persona()
    system = build_system_prompt(persona, mode)

    messages = [{"role": "system", "content": system}]
    for msg in history:
        role = "assistant" if msg["sender"] == "me" else "user"
        messages.append({"role": role, "content": msg["text"]})
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})

    response = await get_client().chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=messages,
        max_tokens=150,
        temperature=0.85,
    )
    return response.choices[0].message.content.strip()
