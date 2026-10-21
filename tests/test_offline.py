"""
Unit test offline — TIDAK membutuhkan GEMINI_API_KEY.
Jalankan: pytest -q
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import llm, router
from app.router import extract_ticket_id, keyword_intent
from app.tools import get_ticket_status


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm, "_client", None)


# ---------- tools.get_ticket_status ----------

def test_ticket_found():
    out = get_ticket_status("TICKET-0005")
    assert "TICKET-0005" in out and "Diproses" in out and "2026-08-27" in out


def test_ticket_case_insensitive():
    assert "Selesai" in get_ticket_status("  ticket-0001 ")


def test_ticket_not_found():
    out = get_ticket_status("TICKET-9999")
    assert "tidak ditemukan" in out


@pytest.mark.parametrize("value", [None, "", "   "])
def test_ticket_missing_id(value):
    assert "TICKET-XXXX" in get_ticket_status(value)


# ---------- router.extract_ticket_id ----------

@pytest.mark.parametrize("query,expected", [
    ("apa status TICKET-0042 saya?", "TICKET-0042"),
    ("cek ticket 42", "TICKET-0042"),
    ("TICKET-42 sudah sampai mana", "TICKET-0042"),
    ("tiket #5 gimana?", "TICKET-0005"),
    ("status tiket no. 7", "TICKET-0007"),
    ("ticket0013", "TICKET-0013"),
    ("berapa jatah cuti saya?", None),
    ("cek status tiket saya", None),
    ("", None),
])
def test_extract_ticket_id(query, expected):
    assert extract_ticket_id(query) == expected


# ---------- router.keyword_intent ----------

@pytest.mark.parametrize("query,expected", [
    ("Apa status tiket TICKET-0005 saya?", "ticket_status"),
    ("tolong cek status tiket saya", "ticket_status"),
    ("Berapa jatah cuti tahunan saya?", "faq"),
    ("Bagaimana cara reset password VPN?", "faq"),
    ("Bagaimana cara mengajukan laptop baru lewat tiket IT?", "faq"),
    ("resep nasi goreng yang enak", "unknown"),
    ("cuaca besok bagaimana?", "unknown"),
])
def test_keyword_intent(query, expected):
    assert keyword_intent(query) == expected


def test_llm_failure_falls_back_to_keyword(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")

    def boom(*args, **kwargs):
        raise llm.LLMUnavailableError("simulasi LLM down")

    monkeypatch.setattr(router, "generate_text", boom)
    assert asyncio.run(router.detect_intent("berapa jatah cuti?")) == "faq"
    assert asyncio.run(router.detect_intent("resep nasi goreng")) == "unknown"


def test_llm_intent_used_when_available(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    monkeypatch.setattr(router, "generate_text", lambda *a, **k: "unknown")
    assert asyncio.run(router.detect_intent("kantor punya kebijakan soal kucing?")) == "unknown"


# ---------- API /ask tanpa API key ----------

@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_ticket_found(client):
    r = client.post("/ask", json={"query": "Apa status tiket TICKET-0005 saya?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success" and body["intent"] == "ticket_status"
    assert "Diproses" in body["data"]


def test_api_ticket_not_found(client):
    body = client.post("/ask", json={"query": "cek ticket 9999"}).json()
    assert body["intent"] == "ticket_status" and "tidak ditemukan" in body["data"]


def test_api_ticket_without_id(client):
    body = client.post("/ask", json={"query": "cek status tiket saya dong"}).json()
    assert body["status"] == "need_info" and body["intent"] == "ticket_status"


def test_api_faq_without_key_is_structured_error(client):
    r = client.post("/ask", json={"query": "Berapa jatah cuti tahunan?"})
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "error" and body["intent"] == "faq"


def test_api_out_of_scope(client):
    body = client.post("/ask", json={"query": "resep nasi goreng"}).json()
    assert body["intent"] == "unknown" and body["status"] == "error"


@pytest.mark.parametrize("payload,code", [({"query": "   "}, 400), ({}, 422), ({"q": 1}, 422)])
def test_api_invalid_input(client, payload, code):
    r = client.post("/ask", json=payload)
    assert r.status_code == code
    assert set(r.json()) == {"status", "intent", "data"}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


# ---------- RAG pipeline (FAISS) dengan embedding palsu, tanpa API ----------

def test_rag_pipeline_with_fake_embeddings(monkeypatch):
    """Memverifikasi build_index + semantic_search + threshold memakai embedding
    bag-of-words deterministik sebagai pengganti Gemini."""
    import re as _re

    import faiss
    import numpy as np

    from app import rag

    vocab = {}

    def fake_embed(texts, task_type):
        dim = 512
        mat = np.zeros((len(texts), dim), dtype="float32")
        for i, t in enumerate(texts):
            for w in _re.findall(r"\w+", t.lower()):
                mat[i, vocab.setdefault(w, len(vocab) % dim)] += 1.0
        faiss.normalize_L2(mat)
        return mat

    monkeypatch.setattr(rag, "_embed", fake_embed)
    monkeypatch.setattr(rag, "_index", None)
    monkeypatch.setattr(rag, "generate_text", lambda prompt, **k: "JAWABAN-LLM")

    rag.build_index()
    assert rag._index.ntotal == 31

    hits = rag.semantic_search("berapa jatah cuti tahunan karyawan tetap", top_k=3)
    assert hits[0]["faq_id"] == 1
    assert hits[0]["score"] >= hits[-1]["score"]

    prompt = rag.build_prompt("jatah cuti?", hits)
    for section in ("### Persona", "### Task", "### Context", "### Format"):
        assert section in prompt

    monkeypatch.setattr(rag, "SIMILARITY_THRESHOLD", 0.2)
    assert asyncio.run(rag.answer_from_knowledge_base("berapa jatah cuti tahunan karyawan tetap")) == "JAWABAN-LLM"
    assert asyncio.run(rag.answer_from_knowledge_base("zzz qqq xyz")) == rag.FALLBACK_ANSWER
    monkeypatch.setattr(rag, "_index", None)
