# Hasil Pengujian 5 Skenario `/ask`

- Waktu uji: 2026-10-21 13:55:07
- Base URL: `http://localhost:8000`
- Router tepat: 5/5

| # | Kategori | Query | Intent diharapkan | HTTP | status | intent | Router tepat? | Waktu (s) | data |
|---|---|---|---|---|---|---|---|---|---|
| 1 | RAG (kebijakan) | Berapa jatah cuti tahunan untuk karyawan tetap? | `faq` | 503 | `error` | `faq` | ✅ | 0.19 | Layanan AI sedang tidak dapat merespons, sehingga pertanyaan kebijakan belum bisa dijawab. Silakan coba lagi nanti atau hubungi tim IT/HR. (Detail: GEMINI_API_KEY belum diatur. Salin .env.example menjadi .env lalu isi API key.) |
| 2 | RAG (kebijakan) | Bagaimana cara reset password VPN perusahaan? | `faq` | 503 | `error` | `faq` | ✅ | 0.00 | Layanan AI sedang tidak dapat merespons, sehingga pertanyaan kebijakan belum bisa dijawab. Silakan coba lagi nanti atau hubungi tim IT/HR. (Detail: GEMINI_API_KEY belum diatur. Salin .env.example menjadi .env lalu isi API key.) |
| 3 | Tool call (tiket ada) | Apa status tiket TICKET-0005 saya? | `ticket_status` | 200 | `success` | `ticket_status` | ✅ | 0.00 | Tiket TICKET-0005 (Access) atas nama Dedi Kurniawan: "Reset password VPN gagal terus". Status: Diproses. Terakhir diperbarui: 2026-08-27. |
| 4 | Tool call (tiket tidak ada) | Tolong cek status TICKET-9999 | `ticket_status` | 200 | `success` | `ticket_status` | ✅ | 0.00 | Tiket TICKET-9999 tidak ditemukan di sistem. Pastikan nomor tiket sudah benar, atau hubungi tim IT Support. |
| 5 | Ambigu / di luar cakupan | Bagaimana resep nasi goreng yang enak? | `unknown` | 200 | `error` | `unknown` | ✅ | 0.00 | Maaf, permintaan Anda di luar cakupan asisten helpdesk ini. Saya dapat membantu pertanyaan kebijakan HR/IT (cuti, password, VPN, perangkat, dll.) atau cek status tiket (contoh: 'status TICKET-0005'). |
