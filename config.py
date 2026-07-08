import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN topilmadi! .env faylida BOT_TOKEN=your_token_here deb yozing."
    )

# OpenSubtitles.com API sozlamalari (subtitr qidirish/yuklash uchun)
OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY")
OPENSUBTITLES_USERNAME = os.getenv("OPENSUBTITLES_USERNAME")  # ixtiyoriy
OPENSUBTITLES_PASSWORD = os.getenv("OPENSUBTITLES_PASSWORD")  # ixtiyoriy

# Anthropic API kaliti (ingliz subtitrni o'zbek tiliga Claude orqali tarjima qilish uchun)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Tarjima uchun ishlatiladigan model — Haiku eng arzon va tez, sifat ham yaxshi
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Yuklab olingan fayllar vaqtincha saqlanadigan papka
DOWNLOADS_DIR = "downloads"

# Telegram oddiy botlar uchun fayl yuborish chegarasi (baytlarda) — 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024
