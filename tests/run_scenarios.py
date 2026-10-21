"""
Menjalankan 5 skenario uji wajib terhadap endpoint /ask dan menyimpan hasilnya
ke tests/results.md.

Pemakaian (server harus sudah berjalan, lokal atau Docker):
    python tests/run_scenarios.py                       # default http://localhost:8000
    python tests/run_scenarios.py --base-url http://localhost:8000
"""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

SCENARIOS = [
    # (no, kategori, query, intent yang diharapkan)
    (1, "RAG (kebijakan)", "Berapa jatah cuti tahunan untuk karyawan tetap?", "faq"),
    (2, "RAG (kebijakan)", "Bagaimana cara reset password VPN perusahaan?", "faq"),
    (3, "Tool call (tiket ada)", "Apa status tiket TICKET-0005 saya?", "ticket_status"),
    (4, "Tool call (tiket tidak ada)", "Tolong cek status TICKET-9999", "ticket_status"),
    (5, "Ambigu / di luar cakupan", "Bagaimana resep nasi goreng yang enak?", "unknown"),
]


def call_ask(base_url: str, query: str):
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/ask",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            code, body = resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        code = err.code
        try:
            body = json.loads(err.read())
        except Exception:
            body = {"status": "error", "intent": "-", "data": str(err)}
    except Exception as err:
        code, body = 0, {"status": "error", "intent": "-", "data": f"Tidak bisa terhubung: {err}"}
    return code, body, time.perf_counter() - start


def md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost:8000"))
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "results.md"))
    args = parser.parse_args()

    rows = []
    for no, kategori, query, expected in SCENARIOS:
        code, body, elapsed = call_ask(args.base_url, query)
        routed_ok = body.get("intent") == expected
        rows.append((no, kategori, query, expected, code, body, elapsed, routed_ok))
        print(f"[{no}] {query}\n    HTTP {code} | {json.dumps(body, ensure_ascii=False)}\n")

    lines = [
        "# Hasil Pengujian 5 Skenario `/ask`",
        "",
        f"- Waktu uji: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Base URL: `{args.base_url}`",
        f"- Router tepat: {sum(r[7] for r in rows)}/{len(rows)}",
        "",
        "| # | Kategori | Query | Intent diharapkan | HTTP | status | intent | Router tepat? | Waktu (s) | data |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for no, kategori, query, expected, code, body, elapsed, ok in rows:
        lines.append(
            f"| {no} | {kategori} | {md_escape(query)} | `{expected}` | {code} | "
            f"`{body.get('status')}` | `{body.get('intent')}` | {'✅' if ok else '❌'} | "
            f"{elapsed:.2f} | {md_escape(body.get('data', ''))} |"
        )
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Hasil disimpan ke {args.output}")


if __name__ == "__main__":
    main()
