"""
Entry point aplikasi FastAPI — IT Helpdesk Assistant.

Alur endpoint utama:
  1. Menerima pertanyaan/permintaan dari user
  2. Meneruskan ke router (router.py) untuk menentukan intent
  3. Router memanggil RAG (rag.py) atau tool (tools.py) sesuai intent
  4. Mengembalikan response terstruktur ke client (status, intent, data)

Status yang mungkin: success | need_info | error
"""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # muat .env sebelum modul lain membaca environment variable

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import rag  # noqa: E402
from app.llm import LLMUnavailableError, has_api_key  # noqa: E402
from app.router import handle_query  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("helpdesk")

MAX_QUERY_LENGTH = 1000


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bangun index FAISS sekali saat startup (jika API key tersedia).
    # Jika gagal, aplikasi tetap jalan; index akan dicoba lagi secara lazy.
    if has_api_key():
        try:
            rag.build_index()
            logger.info("Index FAISS siap (%d dokumen).", rag._index.ntotal)
        except Exception as exc:
            logger.warning("Gagal membangun index saat startup: %s", exc)
    else:
        logger.warning("GEMINI_API_KEY belum diatur: jalur FAQ/RAG tidak tersedia, cek tiket tetap jalan.")
    yield


app = FastAPI(title="IT Helpdesk Assistant API", lifespan=lifespan)


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    status: str
    intent: str
    data: str


def _error(http_code: int, intent: str, message: str) -> JSONResponse:
    body = AskResponse(status="error", intent=intent, data=message).model_dump()
    return JSONResponse(status_code=http_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _error(422, "unknown", "Request tidak valid. Kirim JSON dengan format {\"query\": \"...\"}.")


@app.get("/health")
async def health():
    """Endpoint sederhana untuk memastikan service berjalan."""
    return {"status": "ok", "llm_configured": has_api_key()}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Endpoint utama. Menerima pertanyaan bebas dari user (bisa berupa
    pertanyaan informasi/kebijakan ATAU permintaan cek status tiket),
    lalu meneruskannya ke router untuk diproses.
    """
    query = (request.query or "").strip()
    if not query:
        return _error(400, "unknown", "Query tidak boleh kosong.")
    if len(query) > MAX_QUERY_LENGTH:
        return _error(400, "unknown", f"Query terlalu panjang (maksimal {MAX_QUERY_LENGTH} karakter).")

    try:
        result = await handle_query(query)
    except LLMUnavailableError as exc:
        logger.error("LLM/embedding gagal: %s", exc)
        return _error(
            503,
            "faq",
            "Layanan AI sedang tidak dapat merespons, sehingga pertanyaan kebijakan belum bisa "
            f"dijawab. Silakan coba lagi nanti atau hubungi tim IT/HR. (Detail: {exc})",
        )
    except Exception as exc:  # jaring pengaman terakhir agar API tidak crash
        logger.exception("Error tidak terduga")
        return _error(500, "unknown", f"Terjadi kesalahan internal: {type(exc).__name__}.")

    return AskResponse(**result)
