import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

# AI (OpenAI-compatible: Groq / Ollama / OpenRouter)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")

# Web dashboard
WEB_ENABLED = os.getenv("WEB_ENABLED", "true").lower() == "true"
WEB_PORT = int(os.getenv("WEB_PORT", "8082"))

# Bot behavior
MODE = os.getenv("MODE", "AUTO")  # AUTO | HYBRID | OFF
REPLY_DELAY_MIN = float(os.getenv("REPLY_DELAY_MIN", "15"))
REPLY_DELAY_MAX = float(os.getenv("REPLY_DELAY_MAX", "90"))
SILENCE_TIMEOUT_MINUTES = int(os.getenv("SILENCE_TIMEOUT_MINUTES", "60"))
MAX_MESSAGES_PER_HOUR = int(os.getenv("MAX_MESSAGES_PER_HOUR", "10"))
CONTEXT_WINDOW = 20

# Spam / suspicious detection
SPAM_KEYWORDS = [
    "крипто", "bitcoin", "казино", "заработок", "инвестиц",
    "http://", "https://", "t.me/",
]
SUSPICIOUS_PATTERNS = [r"\d{10,}", r"деньги", r"переведи"]

LEOMATCH_BOT = "leomatchbot"
MATCH_KEYWORDS = {"взаимн", "симпати", "лайк", "match", "💕", "❤️", "🔥", "нравит"}
