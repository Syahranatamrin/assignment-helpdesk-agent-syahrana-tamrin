"""
Router — menentukan apakah query user butuh RAG (informasi/kebijakan)
atau tool call (aksi spesifik, misal cek status tiket).

Pola ini mengikuti workflow router yang sudah dipelajari di Sesi 12.4:
  user input -> intent detection -> jika butuh data -> retrieval (RAG)
                                  -> jika butuh aksi -> tool call

Strategi intent detection (hybrid):
  1. Aturan keyword/regex deterministik untuk ticket_status (ada ID tiket,
     atau kata "tiket" + kata status). Cepat, gratis, dan tidak butuh LLM.
  2. Selain itu, klasifikasi LLM (Gemini) -> 'faq' | 'ticket_status' | 'unknown'.
  3. Jika LLM gagal / API key tidak ada -> fallback ke baseline keyword.
"""

import logging
import re
from typing import Optional

from app.llm import LLMUnavailableError, generate_text, has_api_key
from app.rag import answer_from_knowledge_base
from app.tools import get_ticket_status

logger = logging.getLogger(__name__)

VALID_INTENTS = ("faq", "ticket_status", "unknown")

# "TICKET-0042", "ticket 42", "tiket #42", "tiket no. 42", "TICKET0042", "ticket_42"
TICKET_ID_PATTERN = re.compile(
    r"\b(?:ticket|tiket)\s*[-_#:]?\s*(?:(?:no|nomor|number|nr)\.?\s*)?[-_#:]?\s*(\d{1,6})\b",
    re.IGNORECASE,
)
TICKET_WORD_PATTERN = re.compile(r"\b(?:ticket|tiket)\b", re.IGNORECASE)
STATUS_WORDS = (
    "status", "cek", "check", "progres", "progress", "update", "sampai mana",
    "sudah selesai", "belum selesai", "diproses", "kapan selesai", "lacak", "track",
)
# Kata kunci domain knowledge base (cuti, akses, perangkat, HR, kebijakan, tools).
FAQ_KEYWORDS = (
    "cuti", "izin", "sakit", "absen", "libur", "password", "vpn", "login", "akun",
    "akses", "email", "laptop", "perangkat", "monitor", "software", "instal",
    "resign", "onboarding", "karyawan baru", "gaji", "slip", "rekening", "asuransi",
    "reimburse", "atasan", "hybrid", "wfh", "jam kerja", "lembur", "melahirkan",
    "paternity", "maternity", "aplikasi", "google workspace", "pelatihan", "kebijakan",
    "hr", "it support",
)

INTENT_PROMPT = """Kamu adalah classifier intent untuk asisten helpdesk internal (People & IT Operations).
Klasifikasikan pertanyaan karyawan ke tepat SATU kategori:
- faq: pertanyaan informasi/kebijakan/prosedur umum perusahaan (cuti, izin, password, VPN, akses sistem, perangkat/laptop, gaji, asuransi, reimbursement, jam kerja, lembur, onboarding, tools kolaborasi).
- ticket_status: permintaan mengecek status/progres tiket tertentu milik karyawan.
- unknown: di luar cakupan HR/IT perusahaan (misal resep masakan, cuaca, berita, obrolan umum) atau tidak jelas maksudnya.

Jawab HANYA dengan satu kata: faq, ticket_status, atau unknown.

Pertanyaan: {query}
Kategori:"""


def extract_ticket_id(query: str) -> Optional[str]:
    """
    Mengekstrak ticket_id dari teks dan menormalkannya ke format 'TICKET-XXXX'.
    Contoh: 'ticket 42' -> 'TICKET-0042', 'tiket #5' -> 'TICKET-0005'.
    Mengembalikan None jika tidak ada ticket_id.
    """
    if not query:
        return None
    match = TICKET_ID_PATTERN.search(query)
    if not match:
        return None
    return f"TICKET-{int(match.group(1)):04d}"


def keyword_intent(query: str) -> str:
    """Baseline intent detection berbasis keyword/regex (tanpa LLM)."""
    text = (query or "").lower()
    if extract_ticket_id(text):
        return "ticket_status"
    if TICKET_WORD_PATTERN.search(text) and any(w in text for w in STATUS_WORDS):
        return "ticket_status"
    if any(re.search(rf"\b{re.escape(k)}", text) for k in FAQ_KEYWORDS):
        return "faq"
    return "unknown"


def _parse_llm_intent(raw: str) -> Optional[str]:
    text = raw.strip().lower()
    # Urutan penting: cek 'ticket_status' dulu agar tidak tertukar dengan teks lain.
    for intent in ("ticket_status", "faq", "unknown"):
        if intent in text:
            return intent
    return None


def llm_intent(query: str) -> str:
    """Klasifikasi intent menggunakan Gemini. Melempar LLMUnavailableError bila gagal."""
    raw = generate_text(INTENT_PROMPT.format(query=query), temperature=0.0)
    intent = _parse_llm_intent(raw)
    if intent is None:
        raise LLMUnavailableError(f"Output classifier tidak valid: {raw!r}")
    return intent


async def detect_intent(query: str) -> str:
    """
    Menentukan intent dari query user. Mengembalikan salah satu:
      - "faq"            -> pertanyaan informasi/kebijakan, arahkan ke RAG
      - "ticket_status"  -> permintaan cek status tiket, arahkan ke tool call
      - "unknown"        -> di luar cakupan / tidak dikenali
    """
    baseline = keyword_intent(query)
    # Sinyal tiket yang eksplisit bersifat deterministik: tidak perlu LLM.
    if baseline == "ticket_status":
        return baseline
    if not has_api_key():
        return baseline
    try:
        return llm_intent(query)
    except LLMUnavailableError as exc:
        logger.warning("Intent LLM gagal, fallback ke keyword: %s", exc)
        return baseline


async def handle_query(query: str) -> dict:
    """
    Fungsi utama yang dipanggil oleh endpoint /ask.
    Menjalankan intent detection, lalu merutekan ke RAG atau tool call yang sesuai.
    LLMUnavailableError dari jalur RAG diteruskan ke main.py untuk ditangani.
    """
    intent = await detect_intent(query)

    if intent == "ticket_status":
        ticket_id = extract_ticket_id(query)
        if ticket_id is None:
            return {
                "status": "need_info",
                "intent": "ticket_status",
                "data": get_ticket_status(None),
            }
        return {"status": "success", "intent": "ticket_status", "data": get_ticket_status(ticket_id)}

    if intent == "faq":
        data = await answer_from_knowledge_base(query)
        return {"status": "success", "intent": "faq", "data": data}

    return {
        "status": "error",
        "intent": "unknown",
        "data": (
            "Maaf, permintaan Anda di luar cakupan asisten helpdesk ini. Saya dapat membantu "
            "pertanyaan kebijakan HR/IT (cuti, password, VPN, perangkat, dll.) atau cek status "
            "tiket (contoh: 'status TICKET-0005')."
        ),
    }
