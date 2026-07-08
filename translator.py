import srt
import json
import re
import logging
import asyncio
from typing import Callable, Optional
from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Har bir so'rovda nechta subtitr qatorini birga tarjima qilish
# (kontekstni saqlash uchun guruhlab yuboramiz, lekin juda katta bo'lmasin)
BATCH_SIZE = 40

SYSTEM_PROMPT = (
    "Siz professional subtitr tarjimoni. Sizga ingliz tilidagi film/serial "
    "subtitr qatorlari JSON array shaklida beriladi. Vazifangiz — har birini "
    "tabiiy, ravon va kontekstga mos o'zbek tiliga tarjima qilish. "
    "So'zma-so'z emas, balki tabiiy so'zlashuv uslubida tarjima qiling. "
    "Idioma, hazil va his-tuyg'ularni o'zbek tiliga mos ravishda moslashtiring. "
    "Javobni FAQAT JSON array sifatida qaytaring — xuddi shu tartibda, "
    "xuddi shu sondagi elementlar bilan. Hech qanday qo'shimcha izoh, "
    "tushuntirish yoki markdown belgilari (```) qo'shmang."
)


def _extract_json_array(text: str) -> list[str]:
    """Claude javobidan JSON array'ni ajratib oladi (agar qo'shimcha matn bo'lsa ham)."""
    text = text.strip()
    # Agar ``` bilan o'ralgan bo'lsa, tozalaymiz
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

    # JSON array'ni topishga harakat qilamiz
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)

    return json.loads(text)


def _translate_batch(texts: list[str]) -> list[str]:
    """Bitta so'rovda bir nechta subtitr qatorini tarjima qiladi."""
    user_message = (
        "Quyidagi subtitr qatorlarini o'zbek tiliga tarjima qiling. "
        f"JSON array (ingliz matnlari):\n{json.dumps(texts, ensure_ascii=False)}"
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    result_text = response.content[0].text
    translated = _extract_json_array(result_text)

    if len(translated) != len(texts):
        raise ValueError(
            f"Tarjima natijasi soni mos kelmadi: {len(texts)} kiritildi, "
            f"{len(translated)} qaytdi"
        )

    return translated


def _translate_sync(
    srt_text: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Ingliz tilidagi SRT formatidagi subtitr matnini qabul qilib,
    Claude AI orqali o'zbek tiliga tarjima qilingan SRT matnini qaytaradi.
    """
    subtitles = list(srt.parse(srt_text))

    if not subtitles:
        raise ValueError("SRT fayl bo'sh yoki noto'g'ri formatda")

    total = len(subtitles)

    for i in range(0, total, BATCH_SIZE):
        batch = subtitles[i:i + BATCH_SIZE]
        original_texts = [sub.content.strip() for sub in batch]

        try:
            translated_texts = _translate_batch(original_texts)
            for sub, translated in zip(batch, translated_texts):
                if translated:
                    sub.content = translated
        except Exception:
            logger.exception(f"Tarjima xatosi (batch {i}-{i + len(batch)})")
            # Xatolik bo'lsa, shu guruhning original matnini qoldiramiz

        if progress_callback:
            progress_callback(min(i + BATCH_SIZE, total), total)

    return srt.compose(subtitles)


async def translate_srt_content(
    srt_text: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Async wrapper — bloklovchi tarjima jarayonini alohida thread'da ishga tushiradi."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _translate_sync, srt_text, progress_callback
    )
    return result
