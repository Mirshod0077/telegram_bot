import re
import os
import uuid
import asyncio
import yt_dlp

from config import DOWNLOADS_DIR

# Oddiy URL formatini tekshirish uchun (http/https bilan boshlanishi kifoya)
URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)

# Cookie fayl yo'li — ikki usuldan biri bilan beriladi:
# 1) YT_COOKIES_CONTENT — Railway "Variables" bo'limiga faylning butun matnini joylashtirasiz
#    (eng oson usul, Volume yoki CLI kerak emas)
# 2) YT_COOKIES_FILE — agar Volume ishlatilsa, faylning to'liq yo'li (masalan /data/cookies.txt)
COOKIES_FILE = os.environ.get("YT_COOKIES_FILE", "cookies.txt")

_cookies_content = os.environ.get("YT_COOKIES_CONTENT")
if _cookies_content:
    # Har safar ishga tushganda faylni qayta yozib qo'yamiz (ephemeral disk uchun mos)
    COOKIES_FILE = os.path.join(DOWNLOADS_DIR, "cookies.txt")
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(_cookies_content)


def is_valid_url(url: str) -> bool:
    """Berilgan matn to'g'ri URL formatida ekanini tekshiradi (platformaga qaramasdan)."""
    return bool(URL_PATTERN.match(url.strip()))


def _build_ydl_opts(mode: str, output_template: str) -> dict:
    """
    mode: 'video' yoki 'audio'
    Video uchun eng yaxshi sifatni, audio uchun mp3 formatini tanlaydi.
    """
    base_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    # Agar cookie fayli mavjud bo'lsa, uni qo'shamiz (YouTube "sign in to confirm
    # you're not a bot" xatosini oldini olish uchun)
    if os.path.exists(COOKIES_FILE):
        base_opts["cookiefile"] = COOKIES_FILE

    if mode == "audio":
        base_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:  # video
        # 50MB chegarasidan oshib ketmasligi uchun sifatni cheklaymiz
        base_opts.update({
            "format": "best[filesize<50M]/best",
        })

    return base_opts


def _download_sync(url: str, mode: str) -> str:
    """Sinxron yuklab olish funksiyasi (thread'da ishga tushiriladi)."""
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOADS_DIR, f"{file_id}.%(ext)s")

    ydl_opts = _build_ydl_opts(mode, output_template)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        # Audio holatida kengaytma mp3'ga o'zgaradi (postprocessor tomonidan)
        if mode == "audio":
            base, _ = os.path.splitext(filename)
            mp3_path = base + ".mp3"
            if os.path.exists(mp3_path):
                filename = mp3_path

        return filename


async def download_media(url: str, mode: str) -> str:
    """
    Asosiy async funksiya — bot handler'idan chaqiriladi.
    yt-dlp bloklovchi (sync) kutubxona bo'lgani uchun thread pool'da ishga tushiramiz.
    """
    loop = asyncio.get_event_loop()
    filepath = await loop.run_in_executor(None, _download_sync, url, mode)
    return filepath
