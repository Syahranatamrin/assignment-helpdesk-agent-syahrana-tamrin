# AI Helpdesk Assistant — RAG + Mini-Agent Router (FastAPI + FAISS + Gemini + Docker)

**Repository:** `assignment-helpdesk-agent-syahrana-tamrin`
**Peserta:** Syahrana Tamrin — AI Engineering Bootcamp, Individual Assignment *End-to-End RAG & AI Agent Development*

Backend API yang menggabungkan **RAG** (menjawab pertanyaan kebijakan HR/IT dari knowledge base) dan **workflow routing / tool call** (mengecek status tiket dari data mock) dalam satu endpoint `/ask`, dikelola dengan environment variables, dan dikemas dalam container Docker.

---

## 1. Problem Statement

### Objective
Tim People & IT Operations menerima ratusan pertanyaan repetitif setiap hari. Tujuan prototype ini adalah **mengotomatiskan jawaban** atas pertanyaan tersebut dalam satu sistem yang:
1. menjawab pertanyaan kebijakan/informasi berdasarkan knowledge base resmi (bukan karangan LLM), dan
2. mengenali permintaan yang butuh **data spesifik** (status tiket) lalu mengambilnya lewat **tool call** yang deterministik, bukan lewat pencarian semantik.

### Dua jenis permintaan user

| Jenis | Intent | Ditangani oleh | Contoh |
|---|---|---|---|
| Pertanyaan informasi/kebijakan | `faq` | RAG (FAISS + Gemini) | "Berapa jatah cuti tahunan saya?", "Bagaimana cara reset password VPN?", "Apakah perusahaan menyediakan asuransi kesehatan?" |
| Cek status tiket | `ticket_status` | Tool call `get_ticket_status()` (pandas → `mock_tickets.csv`) | "Apa status tiket TICKET-0005 saya?", "tiket 11 sudah sampai mana?" |
| *(tambahan)* Di luar cakupan / ambigu | `unknown` | Pesan penolakan sopan | "Bagaimana resep nasi goreng yang enak?", "cuaca besok bagaimana?" |

### Asumsi & batasan
- Sumber kebenaran hanya `data/it_helpdesk_knowledge_base.csv` (31 FAQ) dan `data/mock_tickets.csv` (15 tiket, `TICKET-0001` s/d `TICKET-0015`). Tidak ada data tambahan.
- Format ID tiket resmi `TICKET-XXXX` (4 digit). Variasi penulisan seperti `ticket 42`, `tiket #5`, `TICKET-42` dinormalkan ke `TICKET-0042`.
- Tidak ada autentikasi: sistem tidak memverifikasi bahwa tiket benar milik penanya (prototype).
- Satu query = satu intent. Query yang menggabungkan dua permintaan sekaligus akan diproses sesuai intent yang terdeteksi lebih dulu.
- Bahasa utama: Bahasa Indonesia.
- Tidak di-deploy ke cloud; cukup berjalan lokal / dalam container.

---

## 2. Desain Workflow

### Diagram (Mermaid)

```mermaid
flowchart TD
    A[Client: POST /ask {query}] --> B{Validasi input<br/>query kosong?}
    B -- kosong --> E1[400 status=error]
    B -- valid --> C[Intent detection<br/>router.detect_intent]
    C --> C1{Regex/keyword:<br/>ada ID tiket atau<br/>'tiket' + kata status?}
    C1 -- ya --> T[intent = ticket_status]
    C1 -- tidak --> C2{API key ada?}
    C2 -- ya --> L[Klasifikasi LLM Gemini<br/>faq / ticket_status / unknown]
    C2 -- tidak --> K[Baseline keyword domain]
    L -- LLM gagal --> K
    L --> D{intent?}
    K --> D
    T --> X[extract_ticket_id → TICKET-XXXX]
    X -- tidak ada ID --> N[status=need_info<br/>minta nomor tiket]
    X -- ada ID --> TC[Tool call: get_ticket_status<br/>pandas lookup mock_tickets.csv]
    D -- ticket_status --> X
    D -- faq --> R1[Embedding query gemini-embedding-001]
    R1 --> R2[FAISS IndexFlatIP top-3<br/>cosine similarity]
    R2 --> R3{skor ≥ threshold?}
    R3 -- tidak --> R5[Jawaban 'tidak tahu,<br/>hubungi IT/HR']
    R3 -- ya --> R4[Prompt Persona/Task/Context/Format<br/>→ Gemini gemini-2.5-flash]
    D -- unknown --> U[status=error, intent=unknown<br/>pesan di luar cakupan]
    R4 -- LLM gagal --> E2[503 status=error]
    TC --> Z[Response JSON: status, intent, data]
    R4 --> Z
    R5 --> Z
    N --> Z
    U --> Z
```

### Diagram (ASCII)

```
POST /ask {"query": "..."}
        |
        v
 [Validasi input] --kosong--> 400 {status:error}
        |
        v
 [Intent detection]
   1) Regex: TICKET-\d+ / "ticket 42" / "tiket" + kata status ---> ticket_status
   2) selain itu: LLM Gemini -> faq | ticket_status | unknown
   3) LLM gagal / tanpa key -> baseline keyword domain
        |
   +----+--------------------+------------------------+
   |                         |                        |
 ticket_status              faq                    unknown
   |                         |                        |
 extract_ticket_id     embed query (Gemini)     "di luar cakupan"
   |  (tanpa ID ->          |                   status=error
   |   need_info)      FAISS top-3 (cosine)
   v                         |
 get_ticket_status     skor < threshold? --ya--> "tidak tahu, hubungi IT/HR"
 (pandas, CSV)               | tidak
   |                   Prompt P/T/C/F -> Gemini LLM  (gagal -> 503 error)
   |                         |
   +-----------+-------------+
               v
   {"status": "...", "intent": "...", "data": "..."}
```

### Kriteria intent

| Intent | Kriteria | Contoh |
|---|---|---|
| `ticket_status` | Query memuat **ID tiket** (`TICKET-0042`, `ticket 42`, `tiket #5`, `tiket no. 7`) **atau** kata "tiket/ticket" **bersama** kata status (status, cek, progres, update, sampai mana, lacak). Aturan ini deterministik dan diprioritaskan karena butuh data spesifik, bukan informasi umum. | "status TICKET-0005?", "cek status tiket saya" |
| `faq` | Pertanyaan tentang kebijakan/prosedur umum perusahaan: cuti, izin, password, VPN, akses sistem, perangkat, gaji, asuransi, reimbursement, jam kerja, lembur, onboarding, tools kolaborasi. Kata "tiket" **tanpa** kata status juga masuk sini (misal "cara mengajukan laptop lewat tiket IT"). | "berapa jatah cuti?", "cara reset password VPN?" |
| `unknown` | Di luar domain HR/IT perusahaan atau tidak jelas maksudnya (ditentukan LLM; tanpa LLM: tidak ada keyword domain). | "resep nasi goreng", "cuaca besok" |

### Struktur response

```json
{"status": "success | need_info | error", "intent": "faq | ticket_status | unknown", "data": "teks jawaban"}
```

| Kondisi | HTTP | status |
|---|---|---|
| Jawaban berhasil (FAQ / tiket ditemukan / tiket tidak ditemukan) | 200 | `success` |
| Intent tiket tapi tidak ada nomor tiket | 200 | `need_info` |
| Di luar cakupan (`unknown`) | 200 | `error` |
| Query kosong / terlalu panjang | 400 | `error` |
| Body JSON tidak valid | 422 | `error` |
| LLM/embedding gagal (key salah, kuota, jaringan) | 503 | `error` |
| Error tak terduga | 500 | `error` |

---

## 3. Komponen

| File | Isi |
|---|---|
| `app/llm.py` | Gemini client dibuat **lazy** dari `GEMINI_API_KEY` (env), helper `generate_text()`, model dapat diatur via `LLM_MODEL` / `EMBEDDING_MODEL`. |
| `app/rag.py` | Load CSV → dokumen (kategori + pertanyaan + jawaban) → embedding batch `gemini-embedding-001` → normalisasi L2 → `faiss.IndexFlatIP` (cosine). Index dibangun **sekali** saat startup (lifespan) dan di-cache. `semantic_search(query, top_k)`, `build_prompt()` (Persona/Task/Context/Format), `answer_from_knowledge_base()` dengan **similarity threshold** (default 0.70). |
| `app/tools.py` | `get_ticket_status(ticket_id)` — lookup pandas, case-insensitive, aman untuk ID tidak ditemukan / kosong. |
| `app/router.py` | `extract_ticket_id()` (regex + normalisasi), `keyword_intent()` (baseline), `llm_intent()` (klasifikasi Gemini), `detect_intent()` (hybrid + fallback), `handle_query()`. |
| `app/main.py` | FastAPI: `/health`, `/ask`, validasi input, error handling terstruktur, `load_dotenv()`. |
| `tests/test_offline.py` | 34 unit test pytest **tanpa API key** (tools, ekstraksi ID, router keyword, fallback LLM, pipeline FAISS dengan embedding palsu, API). |
| `tests/run_scenarios.py` | Menjalankan 5 skenario wajib ke `/ask` dan menulis `tests/results.md`. |

**Pemilihan threshold 0.70:** diukur dengan `gemini-embedding-001` pada knowledge base ini. Pertanyaan yang relevan mendapat skor teratas ±0.83 ("jatah cuti" → FAQ #1: 0.829, "reset password VPN" → FAQ #8: 0.829), sedangkan pertanyaan di luar KB mendapat 0.56–0.67 ("resep nasi goreng" 0.565, "cuaca besok" 0.623, "fasilitas parkir motor" 0.671). Nilai dapat diubah lewat env `SIMILARITY_THRESHOLD`.

---

## 4. Cara Menjalankan

### Persiapan API key
```bash
cp .env.example .env
# edit .env, isi GEMINI_API_KEY dengan API key milikmu (https://aistudio.google.com/apikey)
```
`.env` sudah masuk `.gitignore` dan `.dockerignore`, jadi tidak ikut ter-commit maupun masuk ke image.

### Lokal (tanpa Docker)
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Dokumentasi interaktif: http://localhost:8000/docs

### Docker
```bash
docker build -t assignment-helpdesk-agent-syahrana-tamrin .
docker run --rm -p 8000:8000 --env-file .env assignment-helpdesk-agent-syahrana-tamrin
# atau tanpa file .env:
# docker run --rm -p 8000:8000 -e GEMINI_API_KEY=$GEMINI_API_KEY assignment-helpdesk-agent-syahrana-tamrin
```
API key diberikan saat **runtime** (`--env-file` / `-e`), tidak di-bake ke dalam image.

### Menguji endpoint
```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Berapa jatah cuti tahunan untuk karyawan tetap?"}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Apa status tiket TICKET-0005 saya?"}'
```

### Menjalankan pengujian
```bash
# Unit test offline (tidak butuh API key)
pip install -r requirements-dev.txt
pytest -q

# 5 skenario end-to-end (server harus berjalan, lokal atau Docker)
python tests/run_scenarios.py --base-url http://localhost:8000
# hasil tersimpan di tests/results.md
```

---

## 5. Hasil Pengujian 5 Skenario

Dijalankan pada 21 Oktober 2026 terhadap server lokal (uvicorn) dengan API key Gemini asli, `LLM_MODEL=gemini-2.5-flash`, `EMBEDDING_MODEL=gemini-embedding-001`. Output mentah ada di [`tests/results.md`](tests/results.md).

| # | Kategori | Query | Intent diharapkan | HTTP | status | intent | Router tepat? | Waktu | Response `data` |
|---|---|---|---|---|---|---|---|---|---|
| 1 | RAG | Berapa jatah cuti tahunan untuk karyawan tetap? | `faq` | 200 | `success` | `faq` | ✅ | 3.05 s | Halo! Karyawan tetap mendapat jatah 12 hari cuti tahunan. Cuti ini dapat diambil setelah masa kerja minimal 3 bulan. |
| 2 | RAG | Bagaimana cara reset password VPN perusahaan? | `faq` | 200 | `success` | `faq` | ✅ | 3.43 s | Halo! Untuk reset password VPN perusahaan, Anda bisa melakukannya secara mandiri melalui portal self-service IT. Jika akun Anda terkunci, silakan hubungi tim IT Support untuk bantuan lebih lanjut. |
| 3 | Tool call (tiket ada) | Apa status tiket TICKET-0005 saya? | `ticket_status` | 200 | `success` | `ticket_status` | ✅ | <0.01 s | Tiket TICKET-0005 (Access) atas nama Dedi Kurniawan: "Reset password VPN gagal terus". Status: Diproses. Terakhir diperbarui: 2026-08-27. |
| 4 | Tool call (tiket tidak ada) | Tolong cek status TICKET-9999 | `ticket_status` | 200 | `success` | `ticket_status` | ✅ | <0.01 s | Tiket TICKET-9999 tidak ditemukan di sistem. Pastikan nomor tiket sudah benar, atau hubungi tim IT Support. |
| 5 | Di luar cakupan | Bagaimana resep nasi goreng yang enak? | `unknown` | 200 | `error` | `unknown` | ✅ | 1.65 s | Maaf, permintaan Anda di luar cakupan asisten helpdesk ini. Saya dapat membantu pertanyaan kebijakan HR/IT (cuti, password, VPN, perangkat, dll.) atau cek status tiket (contoh: 'status TICKET-0005'). |

**Router tepat: 5/5.**

### Hasil uji di dalam container Docker

Image berhasil di-build (`docker build`, Docker 29.7.2, Windows + WSL2, ukuran image ±582 MB) dan container dijalankan dengan `docker run -d -p 8000:8000 --env-file .env`. Endpoint diakses dari luar container (host `localhost:8000`):

- `GET /health` → `{"status":"ok","llm_configured":true}`
- 5 skenario yang sama dijalankan ulang terhadap container: **router tepat 5/5**, jawaban identik dengan run lokal (FAQ ±4–6 s, tiket ±0.01–0.03 s, out-of-scope ±2.3 s). Output mentah: [`tests/results_docker.md`](tests/results_docker.md).

### Uji tambahan (edge case)

| Query | intent | status | Response `data` |
|---|---|---|---|
| cuaca besok bagaimana? | `unknown` | `error` | Pesan di luar cakupan (sama dengan skenario 5). |
| apakah ada fasilitas parkir motor di kantor? | `faq` | `success` | Maaf, saya tidak menemukan informasi tersebut di knowledge base. Silakan hubungi tim IT Support atau HR untuk bantuan lebih lanjut. |
| cek status tiket saya dong | `ticket_status` | `need_info` | Nomor tiket tidak ditemukan dalam pertanyaan Anda. Mohon sebutkan nomor tiket dengan format TICKET-XXXX, misalnya TICKET-0005. |
| tiket 11 sudah sampai mana? | `ticket_status` | `success` | Tiket TICKET-0011 (Network) atas nama Rudi Hartono: "VPN terputus-putus saat WFH". Status: Menunggu Persetujuan. Terakhir diperbarui: 2026-08-25. |
| Bisakah cuti saya dibawa ke tahun depan? | `faq` | `success` | Halo! Ya, sisa cuti Anda dapat dibawa ke tahun berikutnya. Namun, maksimal 6 hari yang bisa dibawa dan harus digunakan dalam kuartal pertama tahun tersebut. |

### Observasi
1. **Router mengarahkan semua skenario ke komponen yang tepat (5/5).** Query dengan ID tiket ditangani regex (tanpa memanggil LLM, latensi <10 ms), sedangkan query lain diklasifikasikan oleh LLM.
2. **Jawaban RAG grounded.** Skenario 1 dan 2 menyalin fakta dari FAQ #1 (12 hari, setelah 3 bulan) dan FAQ #8 (portal self-service IT, hubungi IT Support jika terkunci) tanpa menambah informasi. Parafrase ("dibawa ke tahun depan") tetap menemukan FAQ #3, bukti semantic search bekerja, bukan sekadar pencocokan kata.
3. **Tiket tidak ditemukan tidak membuat aplikasi crash**: tool mengembalikan pesan informatif dengan HTTP 200.
4. **Ketidaktahuan ditangani di dua lapis.** Pertanyaan yang jelas di luar domain (resep, cuaca) ditolak oleh router (`unknown`). Pertanyaan yang tampak HR/IT tetapi tidak ada di KB ("fasilitas parkir") lolos sebagai `faq`, namun skor similarity-nya (0.671) di bawah threshold sehingga sistem menjawab "tidak tahu, hubungi IT/HR" tanpa memanggil LLM, sehingga tidak berhalusinasi.
5. **Latensi:** jalur FAQ ±3 detik (1 panggilan klasifikasi + 1 embedding + 1 generasi), jalur tiket instan, jalur `unknown` ±1.7 detik (1 panggilan klasifikasi).
6. LLM cenderung membuka jawaban dengan "Halo!". Ini kosmetik dan bisa dihilangkan dengan menambah aturan di bagian Format prompt.
7. **Tanpa API key** (lihat [`tests/results_tanpa_api_key.md`](tests/results_tanpa_api_key.md)): skenario tiket dan out-of-scope tetap berjalan via baseline keyword, sedangkan skenario FAQ mengembalikan `503` terstruktur (`status: error`) dan aplikasi tidak crash.

---

## 6. Keterbatasan

- **Ketergantungan pada Gemini API:** jalur FAQ dan klasifikasi intent butuh API key, kuota, dan internet. Jika gagal, klasifikasi jatuh ke baseline keyword dan FAQ mengembalikan error 503.
- **Threshold statis (0.70)** dikalibrasi dari sedikit contoh. Pertanyaan relevan yang diparafrasekan sangat jauh bisa ditolak, dan pertanyaan di luar KB dengan kosakata mirip bisa lolos (LLM tetap diinstruksikan menjawab "tidak tahu").
- **Index FAISS in-memory** dibangun ulang setiap kali aplikasi start (31 dokumen, ±1 detik). Untuk KB besar sebaiknya index disimpan ke disk.
- **Satu intent per query**: "status TICKET-0005 dan berapa jatah cuti?" hanya menjawab bagian tiket.
- **Ekstraksi ID tiket berbasis regex**: hanya ID pertama yang diambil; angka tanpa kata "tiket/ticket" tidak dikenali.
- **Baseline keyword** (dipakai saat LLM tidak tersedia) terbatas pada daftar kata kunci, sehingga query FAQ tanpa kata kunci akan dianggap `unknown`.
- **Tanpa autentikasi/otorisasi** dan tanpa riwayat percakapan (stateless): tidak bisa menjawab lanjutan seperti "kalau yang satunya?".
- Data tiket dibaca dari CSV statis (mock), bukan sistem ticketing sungguhan.

---

## 7. Struktur Project

```
assignment-helpdesk-agent-syahrana-tamrin/
├── app/
│   ├── __init__.py
│   ├── llm.py          # Gemini client (lazy) + konfigurasi model via env
│   ├── main.py         # FastAPI: /health, /ask, error handling
│   ├── rag.py          # embedding, FAISS, semantic search, prompt, LLM answer
│   ├── router.py       # intent detection (regex + LLM) & routing
│   └── tools.py        # tool call: get_ticket_status
├── data/
│   ├── it_helpdesk_knowledge_base.csv
│   └── mock_tickets.csv
├── tests/
│   ├── test_offline.py          # pytest, tanpa API key
│   ├── run_scenarios.py         # 5 skenario end-to-end
│   ├── results.md               # hasil uji dengan API key
│   └── results_tanpa_api_key.md # hasil uji tanpa API key
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements-dev.txt
└── README.md
```
