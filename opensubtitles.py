import requests
import logging

from config import (
    OPENSUBTITLES_API_KEY,
    OPENSUBTITLES_USERNAME,
    OPENSUBTITLES_PASSWORD,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "YuklaBot v1.0"

# Login qilingandan keyingi JWT token shu yerda saqlanadi (jarayon davomida)
_auth_token: str | None = None


def _headers(with_auth: bool = False) -> dict:
    headers = {
        "Api-Key": OPENSUBTITLES_API_KEY,
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }
    if with_auth and _auth_token:
        headers["Authorization"] = f"Bearer {_auth_token}"
    return headers


def login() -> bool:
    """
    Agar .env faylida username/password berilgan bo'lsa, tizimga kirib,
    kunlik yuklab olish limitini oshiradi (5 -> 20 ta/kun).
    Agar berilmagan bo'lsa, shunchaki API key bilan davom etadi.
    """
    global _auth_token

    if not OPENSUBTITLES_USERNAME or not OPENSUBTITLES_PASSWORD:
        return False

    try:
        resp = requests.post(
            f"{BASE_URL}/login",
            headers=_headers(),
            json={"username": OPENSUBTITLES_USERNAME, "password": OPENSUBTITLES_PASSWORD},
            timeout=15,
        )
        resp.raise_for_status()
        _auth_token = resp.json().get("token")
        return bool(_auth_token)
    except Exception:
        logger.exception("OpenSubtitles login muvaffaqiyatsiz")
        return False


def search_subtitles(title: str, lang: str) -> list[dict]:
    """
    Berilgan film nomi va til kodi bo'yicha subtitr qidiradi.
    Qaytaradi: [{"file_id": ..., "movie_name": ..., "release": ..., "language": ...}, ...]
    """
    resp = requests.get(
        f"{BASE_URL}/subtitles",
        headers=_headers(),
        params={"query": title, "languages": lang},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])

    results = []
    for item in data:
        attrs = item.get("attributes", {})
        files = attrs.get("files", [])
        if not files:
            continue
        results.append({
            "file_id": files[0]["file_id"],
            "movie_name": attrs.get("feature_details", {}).get("movie_name") or attrs.get("release", "Noma'lum"),
            "release": attrs.get("release", ""),
            "language": attrs.get("language", lang),
        })
    return results


def get_download_link(file_id: int) -> str:
    """Berilgan file_id uchun haqiqiy yuklab olish linkini oladi."""
    resp = requests.post(
        f"{BASE_URL}/download",
        headers=_headers(with_auth=True),
        json={"file_id": file_id},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["link"]


def download_subtitle_text(file_id: int) -> str:
    """Subtitr faylining matnini (SRT formatida) qaytaradi."""
    link = get_download_link(file_id)
    resp = requests.get(link, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text
