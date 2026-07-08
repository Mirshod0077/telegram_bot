#!/usr/bin/env python3
"""
Ko'p tilli kino uchun tomosha variantlarini avtomatik tayyorlovchi skript.

Kerak: Python 3.8+, ffmpeg va ffprobe PATH'da bo'lishi kerak
       (Windows'da: ffmpeg.exe va ffprobe.exe joylashgan papkani PATH'ga qo'shing)

Ishlatish:
    python make_variants.py "D:/Kinolar/kino.mkv"
    (Windows'da fayl yo'lida orqaga qiyshiq chiziq ishlatsangiz, tirnoq ichiga oling)

Natija (kino fayli joylashgan papkada):
    kino_EN_EN-sub.mp4   -> Ingliz audio + Ingliz subtitr (kuydirilgan)
    kino_UZ_EN-sub.mp4   -> O'zbek audio + Ingliz subtitr (kuydirilgan)
"""

import subprocess
import json
import sys
import os

# --- SOZLAMALAR: kerak bo'lsa shu yerdan o'zgartiring ---
VARIANTS = [
    # (audio_til_kodi, subtitr_til_kodi, fayl_nomiga_qo'shimcha)
    ("eng", "eng", "EN_EN-sub"),
    ("uzb", "eng", "UZ_EN-sub"),
]

# Video sifati sozlamalari (kerak bo'lsa o'zgartiring)
CRF = "23"          # Faqat CPU rejimida ishlatiladi: 18=yuqori sifat, 28=past sifat
PRESET = "veryfast" # Faqat CPU rejimida ishlatiladi (agar GPU topilmasa)
NVENC_QUALITY = "23"  # GPU rejimida sifat: 18-20=yuqori, 23-25=o'rtacha, 28+=past
NVENC_PRESET = "p5"   # NVIDIA preset: p1(tez/past sifat)...p7(sekin/yuqori sifat)
AUDIO_BITRATE = "128k"

# GPU tezlashtirishni avtomatik yoqish/o'chirish
USE_HARDWARE_ACCEL = True


def detect_hw_encoder():
    """Mavjud GPU kodlagichni aniqlaydi (NVIDIA -> Intel -> AMD -> yo'q bo'lsa CPU)."""
    if not USE_HARDWARE_ACCEL:
        return None

    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    encoders_output = result.stdout

    candidates = [
        ("h264_nvenc", "NVIDIA (NVENC)"),
        ("h264_qsv", "Intel (QuickSync)"),
        ("h264_amf", "AMD (AMF)"),
    ]

    for encoder_name, label in candidates:
        if encoder_name in encoders_output:
            # Haqiqatan ishlashini tekshirish uchun qisqa test
            test_cmd = [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1",
                "-c:v", encoder_name, "-f", "null", "-"
            ]
            test_result = subprocess.run(
                test_cmd, capture_output=True, encoding="utf-8", errors="replace"
            )
            if test_result.returncode == 0:
                print(f"GPU tezlashtirish topildi: {label} ({encoder_name})\n")
                return encoder_name
            else:
                print(f"{label} topildi, lekin ishlamadi (drayver muammosi bo'lishi mumkin), o'tkazib yuborilyapti")

    print("GPU tezlashtirish topilmadi, protsessor (CPU) orqali kodlanadi\n")
    return None

# Ba'zi tillar uchun mumkin bo'lgan kod variantlari (ffprobe har xil kodlashi mumkin)
LANG_ALIASES = {
    "eng": ["eng", "en"],
    "uzb": ["uzb", "uz"],
    "rus": ["rus", "ru"],
}


def probe_streams(filepath):
    """ffprobe orqali audio va subtitr streamlarini til bilan birga oladi."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", filepath
    ]
    result = subprocess.run(
        cmd, capture_output=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        print(f"XATO: ffprobe ishlamadi:\n{result.stderr}")
        sys.exit(1)

    data = json.loads(result.stdout)
    audio_streams = []
    subtitle_streams = []

    audio_idx = 0
    subtitle_idx = 0
    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        lang = stream.get("tags", {}).get("language", "und").lower()
        if codec_type == "audio":
            audio_streams.append({"relative_index": audio_idx, "lang": lang})
            audio_idx += 1
        elif codec_type == "subtitle":
            subtitle_streams.append({"relative_index": subtitle_idx, "lang": lang})
            subtitle_idx += 1

    return audio_streams, subtitle_streams


def find_stream_index(streams, lang_code, stream_type):
    """Berilgan til kodiga mos stream indeksini topadi (alias'larni ham tekshiradi)."""
    aliases = LANG_ALIASES.get(lang_code, [lang_code])
    for s in streams:
        if s["lang"] in aliases:
            return s["relative_index"]
    print(f"OGOHLANTIRISH: '{lang_code}' tilidagi {stream_type} topilmadi.")
    print(f"   Mavjud tillar: {[s['lang'] for s in streams]}")
    return None


def build_output_path(input_path, suffix):
    base, _ = os.path.splitext(input_path)
    return f"{base}_{suffix}.mp4"


def make_variant(input_path, audio_lang, sub_lang, suffix, audio_streams, subtitle_streams, hw_encoder):
    audio_idx = find_stream_index(audio_streams, audio_lang, "audio")
    sub_idx = find_stream_index(subtitle_streams, sub_lang, "subtitr")

    if audio_idx is None or sub_idx is None:
        print(f"O'TKAZIB YUBORILDI: {suffix} (kerakli til topilmadi)\n")
        return False

    output_path = build_output_path(input_path, suffix)

    # Windows yo'llarida ffmpeg subtitles filtri uchun maxsus escape kerak
    escaped_input = input_path.replace("\\", "/").replace(":", "\\:")

    if hw_encoder == "h264_nvenc":
        video_codec_args = ["-c:v", "h264_nvenc", "-cq", NVENC_QUALITY, "-preset", NVENC_PRESET]
    elif hw_encoder == "h264_qsv":
        video_codec_args = ["-c:v", "h264_qsv", "-global_quality", NVENC_QUALITY]
    elif hw_encoder == "h264_amf":
        video_codec_args = ["-c:v", "h264_amf", "-qp_i", NVENC_QUALITY, "-qp_p", NVENC_QUALITY]
    else:
        video_codec_args = ["-c:v", "libx264", "-crf", CRF, "-preset", PRESET]

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-map", "0:v:0",
        "-map", f"0:a:{audio_idx}",
        "-vf", f"subtitles='{escaped_input}':si={sub_idx}",
        *video_codec_args,
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        output_path
    ]

    print(f"Tayyorlanmoqda: {output_path}")
    print(f"   (audio: {audio_lang}, subtitr: {sub_lang} — kuydirilgan)")

    result = subprocess.run(
        cmd, capture_output=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        print(f"XATO yuz berdi:\n{result.stderr[-1500:]}")
        return False

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"TAYYOR: {output_path} ({size_mb:.0f} MB)\n")
    return True


def main():
    if len(sys.argv) < 2:
        print("Ishlatish: python make_variants.py \"kino_fayli_yoli.mkv\"")
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.isfile(input_path):
        print(f"XATO: fayl topilmadi: {input_path}")
        sys.exit(1)

    hw_encoder = detect_hw_encoder()

    print(f"Tahlil qilinmoqda: {input_path}\n")
    audio_streams, subtitle_streams = probe_streams(input_path)

    print(f"Topilgan audio tillar: {[s['lang'] for s in audio_streams]}")
    print(f"Topilgan subtitr tillar: {[s['lang'] for s in subtitle_streams]}\n")

    success_count = 0
    for audio_lang, sub_lang, suffix in VARIANTS:
        if make_variant(input_path, audio_lang, sub_lang, suffix, audio_streams, subtitle_streams, hw_encoder):
            success_count += 1

    print(f"Yakun: {success_count}/{len(VARIANTS)} variant muvaffaqiyatli tayyorlandi.")


if __name__ == "__main__":
    main()
