import asyncio
import logging
import os
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
    BufferedInputFile,
)
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, MAX_FILE_SIZE
from downloader import is_valid_url, download_media
import opensubtitles
from translator import translate_srt_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Har bir foydalanuvchi yuborgan oxirgi linkni vaqtincha xotirada saqlaymiz
# (kalit: user_id, qiymat: url)
user_links: dict[int, str] = {}

# Har bir foydalanuvchining subtitr qidiruv natijalarini saqlab turamiz
# (kalit: user_id, qiymat: {"results": [...], "mode": "direct" | "translate", "movie": str})
user_subtitle_search: dict[int, dict] = {}


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Salom! 👋\n\n"
        "📥 Menga istalgan sayt (YouTube, Instagram, TikTok, Facebook, "
        "Twitter/X, Vimeo, SoundCloud va boshqalar) linkini yuboring — "
        "men uni video yoki mp3 (musiqa) shaklida yuklab beraman.\n\n"
        "🎬 Yoki /subtitle <film nomi> buyrug'i orqali film subtitrini "
        "o'zbek tilida topib beraman (masalan: /subtitle Interstellar)\n\n"
        "Boshlash uchun shunchaki link yuboring yoki /subtitle buyrug'ini ishlating! 🔗"
    )


@dp.message(F.text.startswith("http"))
async def handle_link(message: Message):
    url = message.text.strip()

    if not is_valid_url(url):
        await message.answer(
            "❌ Bu to'g'ri link ko'rinmayapti. Iltimos, to'liq linkni yuboring."
        )
        return

    user_links[message.from_user.id] = url

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎥 Video", callback_data="mode:video"),
            InlineKeyboardButton(text="🎵 Musiqa (MP3)", callback_data="mode:audio"),
        ]
    ])

    await message.answer(
        "✅ Link qabul qilindi!\n"
        "Qaysi formatda yuklab olay?",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("mode:"))
async def handle_mode_choice(callback: CallbackQuery):
    user_id = callback.from_user.id
    url = user_links.get(user_id)

    if not url:
        await callback.answer("Link topilmadi, iltimos qaytadan yuboring.", show_alert=True)
        return

    mode = callback.data.split(":")[1]  # "video" yoki "audio"

    await callback.message.edit_text("⏳ Yuklab olinmoqda, biroz kuting...")
    await callback.answer()

    filepath = None
    try:
        filepath = await download_media(url, mode)

        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            await callback.message.edit_text(
                "❌ Fayl juda katta (50MB dan oshiq). "
                "Kichikroq video bilan urinib ko'ring."
            )
            return

        input_file = FSInputFile(filepath)

        if mode == "audio":
            await callback.message.answer_audio(input_file)
        else:
            await callback.message.answer_video(input_file)

        await callback.message.edit_text("✅ Tayyor!")

    except Exception as e:
        logger.exception("Yuklab olishda xatolik")
        await callback.message.edit_text(
            "❌ Yuklab olishda xatolik yuz berdi.\n"
            "Ehtimol bu sayt qo'llab-quvvatlanmaydi, kontent yopiq/xususiy, "
            "yoki link noto'g'ri. Boshqa link bilan urinib ko'ring."
        )
    finally:
        # Vaqtinchalik faylni tozalash
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        user_links.pop(user_id, None)


@dp.message(Command("subtitle"))
async def cmd_subtitle(message: Message):
    # "/subtitle Interstellar" -> "Interstellar"
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Film nomini ham yozing. Masalan:\n"
            "<code>/subtitle Interstellar</code>",
            parse_mode="HTML",
        )
        return

    movie_name = parts[1].strip()
    user_id = message.from_user.id

    status_msg = await message.answer(f"🔍 \"{movie_name}\" qidirilmoqda...")

    try:
        # Avval o'zbekcha subtitrni qidiramiz
        uz_results = await asyncio.to_thread(opensubtitles.search_subtitles, movie_name, "uz")

        if uz_results:
            user_subtitle_search[user_id] = {
                "results": uz_results[:5],
                "mode": "direct",
                "movie": movie_name,
            }
            await _show_subtitle_choices(status_msg, uz_results[:5], "🇺🇿 O'zbekcha subtitr topildi!")
            return

        # Topilmasa, inglizcha subtitrni qidiramiz (keyin tarjima qilamiz)
        en_results = await asyncio.to_thread(opensubtitles.search_subtitles, movie_name, "en")

        if en_results:
            user_subtitle_search[user_id] = {
                "results": en_results[:5],
                "mode": "translate",
                "movie": movie_name,
            }
            await _show_subtitle_choices(
                status_msg,
                en_results[:5],
                "ℹ️ O'zbekcha subtitr topilmadi.\n"
                "Inglizcha subtitr topildi — Claude AI orqali tarjima qilib beraman:",
            )
            return

        await status_msg.edit_text(
            f"❌ \"{movie_name}\" uchun na o'zbekcha, na inglizcha subtitr topilmadi.\n"
            "Film nomini boshqacha yozib ko'ring (masalan original nomida)."
        )

    except Exception:
        logger.exception("Subtitr qidirishda xatolik")
        await status_msg.edit_text(
            "❌ Qidirishda xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
        )


async def _show_subtitle_choices(status_msg: Message, results: list[dict], header: str):
    """Topilgan subtitr variantlarini tugmalar shaklida ko'rsatadi."""
    buttons = []
    for idx, item in enumerate(results):
        label = item["movie_name"] or item["release"] or f"Variant {idx + 1}"
        label = label[:50]  # Telegram tugma matni uzunligi chegarasi
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"sub:{idx}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await status_msg.edit_text(
        f"{header}\n\nQaysi natijani tanlaysiz?",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("sub:"))
async def handle_subtitle_choice(callback: CallbackQuery):
    user_id = callback.from_user.id
    search_data = user_subtitle_search.get(user_id)

    if not search_data:
        await callback.answer("Qidiruv topilmadi, iltimos qaytadan qidiring.", show_alert=True)
        return

    idx = int(callback.data.split(":")[1])
    results = search_data["results"]

    if idx >= len(results):
        await callback.answer("Bu variant topilmadi.", show_alert=True)
        return

    selected = results[idx]
    mode = search_data["mode"]
    movie_name = search_data["movie"]

    await callback.answer()

    try:
        if mode == "direct":
            # To'g'ridan-to'g'ri o'zbekcha subtitrni yuklab yuboramiz
            await callback.message.edit_text("⏳ O'zbekcha subtitr yuklab olinmoqda...")
            subtitle_text = await asyncio.to_thread(
                opensubtitles.download_subtitle_text, selected["file_id"]
            )
            file_bytes = subtitle_text.encode("utf-8")
            filename = f"{movie_name}_uz.srt"

            await callback.message.answer_document(
                BufferedInputFile(file_bytes, filename=filename)
            )
            await callback.message.edit_text("✅ Tayyor!")

        else:  # mode == "translate"
            await callback.message.edit_text(
                "⏳ Inglizcha subtitr yuklab olinmoqda..."
            )
            subtitle_text = await asyncio.to_thread(
                opensubtitles.download_subtitle_text, selected["file_id"]
            )

            await callback.message.edit_text(
                "🤖 Claude AI orqali tarjima qilinmoqda...\n"
                "Bu bir necha daqiqa vaqt olishi mumkin, biroz kuting."
            )

            last_update_time = [0.0]
            main_loop = asyncio.get_event_loop()

            async def _safe_edit(text: str):
                try:
                    await callback.message.edit_text(text)
                except Exception:
                    pass  # Masalan "xabar o'zgarmagan" kabi kichik xatolarni e'tiborsiz qoldiramiz

            def progress_callback(current: int, total: int):
                # Har 3 sekundda bir marta xabarni yangilaymiz (Telegram limitiga tushmaslik uchun)
                now = time.time()
                if now - last_update_time[0] < 3:
                    return
                last_update_time[0] = now
                percent = int(current / total * 100)
                asyncio.run_coroutine_threadsafe(
                    _safe_edit(f"🤖 Tarjima qilinmoqda... {percent}% ({current}/{total} qator)"),
                    main_loop,
                )

            translated_srt = await translate_srt_content(subtitle_text, progress_callback)

            file_bytes = translated_srt.encode("utf-8")
            filename = f"{movie_name}_uz_AI.srt"

            await callback.message.answer_document(
                BufferedInputFile(file_bytes, filename=filename),
                caption="ℹ️ Bu subtitr Claude AI orqali avtomatik tarjima qilingan."
            )
            await callback.message.edit_text("✅ Tayyor!")

    except Exception:
        logger.exception("Subtitr yuklab olish/tarjima qilishda xatolik")
        await callback.message.edit_text(
            "❌ Xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring."
        )
    finally:
        user_subtitle_search.pop(user_id, None)


@dp.message()
async def handle_other(message: Message):
    await message.answer(
        "Menga video/musiqa linkini yuboring, yoki film subtitrini olish uchun:\n"
        "<code>/subtitle Film nomi</code>",
        parse_mode="HTML",
    )


async def main():
    logger.info("Bot ishga tushmoqda...")
    if opensubtitles.login():
        logger.info("OpenSubtitles'ga muvaffaqiyatli kirildi (kengaytirilgan limit faol)")
    else:
        logger.info("OpenSubtitles login ma'lumotlari yo'q, standart limit bilan ishlaydi (5/kun)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
