"""
Helper bersama untuk Gemini client.

Client dibuat secara lazy (saat pertama kali dibutuhkan), sehingga aplikasi
tetap bisa start dan jalur tool call (cek tiket) tetap berfungsi walaupun
GEMINI_API_KEY belum diisi. API key SELALU dibaca dari environment variable,
tidak pernah di-hardcode.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_LLM_MODEL = "gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"

_client = None


class LLMUnavailableError(RuntimeError):
    """Dilempar ketika LLM/embedding tidak bisa dipanggil (key kosong, API error, dll)."""


def get_llm_model() -> str:
    return os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL


def get_embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL


def has_api_key() -> bool:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return bool(key) and key != "your_key_here"


def get_client():
    """Mengembalikan Gemini client (dibuat sekali, lalu di-cache)."""
    global _client
    if _client is None:
        if not has_api_key():
            raise LLMUnavailableError(
                "GEMINI_API_KEY belum diatur. Salin .env.example menjadi .env lalu isi API key."
            )
        from google import genai

        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
    return _client


def generate_text(prompt: str, temperature: float = 0.2) -> str:
    """Memanggil LLM Gemini dan mengembalikan teks jawaban."""
    from google.genai import types

    client = get_client()
    try:
        response = client.models.generate_content(
            model=get_llm_model(),
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
    except Exception as exc:  # error jaringan, kuota, model tidak ada, dll.
        raise LLMUnavailableError(f"Gagal memanggil LLM: {exc}") from exc

    text = (response.text or "").strip()
    if not text:
        raise LLMUnavailableError("LLM mengembalikan respons kosong.")
    return text
