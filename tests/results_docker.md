# Hasil Pengujian 5 Skenario `/ask`

- Waktu uji: 2026-10-21 14:12:51
- Base URL: `http://localhost:8000`
- Router tepat: 5/5

| # | Kategori | Query | Intent diharapkan | HTTP | status | intent | Router tepat? | Waktu (s) | data |
|---|---|---|---|---|---|---|---|---|---|
| 1 | RAG (kebijakan) | Berapa jatah cuti tahunan untuk karyawan tetap? | `faq` | 200 | `success` | `faq` | ✅ | 4.46 | Halo! Karyawan tetap mendapat jatah 12 hari cuti tahunan. Cuti ini dapat diambil setelah masa kerja minimal 3 bulan. |
| 2 | RAG (kebijakan) | Bagaimana cara reset password VPN perusahaan? | `faq` | 200 | `success` | `faq` | ✅ | 5.85 | Halo! Untuk reset password VPN perusahaan, Anda bisa melakukannya secara mandiri melalui portal self-service IT. Jika akun Anda terkunci, silakan hubungi tim IT Support untuk bantuan lebih lanjut. |
| 3 | Tool call (tiket ada) | Apa status tiket TICKET-0005 saya? | `ticket_status` | 200 | `success` | `ticket_status` | ✅ | 0.03 | Tiket TICKET-0005 (Access) atas nama Dedi Kurniawan: "Reset password VPN gagal terus". Status: Diproses. Terakhir diperbarui: 2026-08-27. |
| 4 | Tool call (tiket tidak ada) | Tolong cek status TICKET-9999 | `ticket_status` | 200 | `success` | `ticket_status` | ✅ | 0.01 | Tiket TICKET-9999 tidak ditemukan di sistem. Pastikan nomor tiket sudah benar, atau hubungi tim IT Support. |
| 5 | Ambigu / di luar cakupan | Bagaimana resep nasi goreng yang enak? | `unknown` | 200 | `error` | `unknown` | ✅ | 2.33 | Maaf, permintaan Anda di luar cakupan asisten helpdesk ini. Saya dapat membantu pertanyaan kebijakan HR/IT (cuti, password, VPN, perangkat, dll.) atau cek status tiket (contoh: 'status TICKET-0005'). |
