# Jurnal Finder — Bulk Downloader + Abstract → Excel

Dua script Python untuk mempercepat penyusunan skripsi:

1. **`journal_dl.py`** — cari paper via Semantic Scholar, cek PDF gratis via
   Unpaywall, download massal, export `hasil_pencarian.csv` + `manual_download.csv`.
2. **`abstract_to_excel.py`** — baca PDF di folder download, extract via
   OpenRouter (DeepSeek free), hasilkan `tabel_perbandingan.xlsx`
   (sheet Tabel Jurnal + Analisis Gap X).

Detail hasil pengujian & root cause ada di [`TEST_REPORT.md`](TEST_REPORT.md).

## Instalasi

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Butuh juga: poppler (untuk pdftotext, opsional tapi disarankan)
# Ubuntu: sudo apt install poppler-utils
```

## Pemakaian

Mode interaktif (dipandu, tanpa argumen):

```bash
python journal_dl.py
```

Mode CLI:

```bash
python journal_dl.py -k "ESG firm value" "Tobin Q" -n 20 -y 2018 2024 -e kamu@email.com
# Dengan API key Semantic Scholar (gratis, hilangkan rate-limit 429):
python journal_dl.py -k "ESG" -n 30 --api-key S2_KEY_KAMU
```

Abstract → Excel (butuh `OPENROUTER_API_KEY`):

```bash
export OPENROUTER_API_KEY=sk-or-xxxx
python abstract_to_excel.py
python abstract_to_excel.py --dir ./jurnal_download --out hasil.xlsx
python abstract_to_excel.py --dir ./jurnal_download --out hasil.xlsx --api-key sk-or-xxxx
```

## Catatan API

- Semantic Scholar tanpa API key kena rate-limit `429` (IP bersama).
  Daftar gratis: https://www.semanticscholar.org/product/api
- Unpaywall butuh email valid di `-e`.
- OpenRouter: https://openrouter.ai/
