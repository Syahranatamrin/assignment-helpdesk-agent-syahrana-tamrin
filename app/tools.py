"""
Modul Tools — fungsi-fungsi "aksi" yang dipanggil router ketika intent
BUKAN pertanyaan informasi/kebijakan, melainkan permintaan spesifik
yang butuh pengecekan data langsung (bukan retrieval semantik).

Pola ini mengikuti konsep Tool Integration di Sesi 12.3.
"""

import os
from functools import lru_cache
from typing import Optional

import pandas as pd

MOCK_TICKETS_PATH = os.environ.get(
    "MOCK_TICKETS_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_tickets.csv"),
)


@lru_cache(maxsize=1)
def _load_tickets(path: str = MOCK_TICKETS_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    df["ticket_id_norm"] = df["ticket_id"].str.strip().str.upper()
    return df


def get_ticket_status(ticket_id: Optional[str]) -> str:
    """
    Mencari status tiket berdasarkan ticket_id pada data mock_tickets.csv.
    Pencarian tidak peka huruf besar/kecil. Tidak pernah melempar exception
    untuk tiket yang tidak ada; selalu mengembalikan pesan yang informatif.
    """
    if not ticket_id or not str(ticket_id).strip():
        return (
            "Nomor tiket tidak ditemukan dalam pertanyaan Anda. "
            "Mohon sebutkan nomor tiket dengan format TICKET-XXXX, misalnya TICKET-0005."
        )

    key = str(ticket_id).strip().upper()
    try:
        df = _load_tickets()
    except Exception as exc:
        return f"Data tiket sedang tidak dapat diakses ({exc}). Silakan coba lagi nanti."

    match = df[df["ticket_id_norm"] == key]
    if match.empty:
        return (
            f"Tiket {key} tidak ditemukan di sistem. Pastikan nomor tiket sudah benar, "
            "atau hubungi tim IT Support."
        )

    row = match.iloc[0]
    return (
        f"Tiket {row['ticket_id']} ({row['category']}) atas nama {row['employee_name']}: "
        f"\"{row['subject']}\". Status: {row['status']}. "
        f"Terakhir diperbarui: {row['last_update']}."
    )
