"""
Modul RAG — mengubah knowledge base menjadi embedding, menyimpannya ke FAISS,
melakukan semantic search, lalu menghasilkan jawaban menggunakan LLM.

Alur:
  load CSV -> unit retrievable (question + answer) -> embedding Gemini
  -> normalisasi L2 -> FAISS IndexFlatIP (inner product = cosine similarity)
  -> semantic_search(query) -> prompt Persona/Task/Context/Format -> LLM.

Index dibangun SEKALI (lazy-loading + cache, dan dipanaskan saat startup FastAPI
bila API key tersedia), bukan di setiap request.
"""

import os
import threading

import faiss
import numpy as np
import pandas as pd

from app.llm import LLMUnavailableError, generate_text, get_client, get_embedding_model

KNOWLEDGE_BASE_PATH = os.environ.get(
    "KNOWLEDGE_BASE_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "it_helpdesk_knowledge_base.csv"),
)

# Ambang minimal cosine similarity agar dokumen dianggap relevan.
# Jika skor dokumen teratas di bawah ambang ini, sistem menjawab "tidak tahu".
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.70"))
EMBED_BATCH_SIZE = 50

FALLBACK_ANSWER = (
    "Maaf, saya tidak menemukan informasi tersebut di knowledge base. "
    "Silakan hubungi tim IT Support atau HR untuk bantuan lebih lanjut."
)

_index = None
_documents = None
_df = None
_lock = threading.Lock()


def load_knowledge_base(path: str = KNOWLEDGE_BASE_PATH) -> pd.DataFrame:
    """Memuat CSV knowledge base dan menyusun teks dokumen yang akan di-embed."""
    df = pd.read_csv(path).fillna("")
    df["document"] = (
        "Kategori: " + df["category"].astype(str)
        + "\nPertanyaan: " + df["question"].astype(str)
        + "\nJawaban: " + df["answer"].astype(str)
    )
    return df


def _embed(texts, task_type: str) -> np.ndarray:
    """Membuat embedding (batch) dengan Gemini, lalu menormalisasi L2."""
    from google.genai import types

    client = get_client()
    vectors = []
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i:i + EMBED_BATCH_SIZE]
            result = client.models.embed_content(
                model=get_embedding_model(),
                contents=batch,
                config=types.EmbedContentConfig(task_type=task_type),
            )
            vectors.extend(e.values for e in result.embeddings)
    except LLMUnavailableError:
        raise
    except Exception as exc:
        raise LLMUnavailableError(f"Gagal membuat embedding: {exc}") from exc

    matrix = np.asarray(vectors, dtype="float32")
    faiss.normalize_L2(matrix)
    return matrix


def _get_embedding(text: str) -> np.ndarray:
    """Embedding untuk satu query (shape: 1 x dim, sudah dinormalisasi)."""
    return _embed([text], task_type="RETRIEVAL_QUERY")


def build_index():
    """Membangun index FAISS dari knowledge base CSV (dipanggil sekali, lalu di-cache)."""
    global _index, _documents, _df
    with _lock:
        if _index is not None:
            return _index
        df = load_knowledge_base()
        documents = df["document"].tolist()
        embeddings = _embed(documents, task_type="RETRIEVAL_DOCUMENT")
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        _df, _documents, _index = df, documents, index
        return _index


def semantic_search(query: str, top_k: int = 3):
    """
    Mencari top_k dokumen paling relevan untuk query.
    Mengembalikan list dict: faq_id, category, question, answer, score (cosine).
    """
    index = build_index()
    query_vec = _get_embedding(query)
    k = min(top_k, index.ntotal)
    scores, ids = index.search(query_vec, k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        row = _df.iloc[int(idx)]
        results.append({
            "faq_id": int(row["faq_id"]),
            "category": row["category"],
            "question": row["question"],
            "answer": row["answer"],
            "score": float(score),
        })
    return results


def build_prompt(query: str, contexts) -> str:
    """Menyusun prompt dengan struktur Persona / Task / Context / Format."""
    context_text = "\n\n".join(
        f"[{i}] (Kategori: {c['category']})\nQ: {c['question']}\nA: {c['answer']}"
        for i, c in enumerate(contexts, start=1)
    )
    return f"""### Persona
Kamu adalah Asisten Helpdesk internal tim People & IT Operations perusahaan.
Kamu ramah, ringkas, dan hanya menjawab berdasarkan dokumen resmi perusahaan.

### Task
Jawab pertanyaan karyawan HANYA berdasarkan informasi pada bagian Context.
Jangan menambahkan informasi, angka, atau prosedur yang tidak ada di Context.
Jika Context tidak memuat jawaban, katakan bahwa kamu tidak tahu dan sarankan
karyawan menghubungi tim IT Support atau HR.

### Context
{context_text}

### Format
- Jawab dalam Bahasa Indonesia, maksimal 3-4 kalimat.
- Langsung ke inti jawaban; gunakan poin/langkah bila prosedurnya bertahap.
- Jangan menyebut nomor dokumen atau istilah "Context".

### Pertanyaan Karyawan
{query}

### Jawaban"""


async def answer_from_knowledge_base(query: str) -> str:
    """
    Dipanggil router.py ketika intent = 'faq'.
    semantic_search -> cek ambang similarity -> build prompt -> panggil LLM.
    Melempar LLMUnavailableError jika embedding/LLM gagal (ditangani di main.py).
    """
    results = semantic_search(query, top_k=3)
    relevant = [r for r in results if r["score"] >= SIMILARITY_THRESHOLD]
    if not relevant:
        return FALLBACK_ANSWER
    return generate_text(build_prompt(query, relevant))
