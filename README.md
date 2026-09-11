# Jurnal Finder — Bulk Downloader + Abstract → Excel

Dua script Python untuk mempercepat penyusunan skripsi:

1. **`journal_dl.py`** — cari paper via **Scopus** + **ScienceDirect**
   (Elsevier API), cek PDF gratis via Unpaywall, download massal,
   export `hasil_pencarian.csv` + `manual_download.csv` (berisi link DOI).
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
python journal_dl.py -k "donchian channel breakout" -n 20 -y 2000 2024 --elsevier-key KEY_KAMU -e kamu@students.undip.ac.id
# Atau via env (tidak perlu --elsevier-key lagi):
export ELSEVIER_API_KEY=KEY_KAMU
python journal_dl.py -k "donchian channel" -n 20 --sources all
# Hanya Scopus:
python journal_dl.py -k "ESG firm value" -n 30 -s scopus
```

## Scopus & ScienceDirect + akses UNDIP

**Daftar API key Elsevier (gratis):** https://dev.elsevier.com → Create API Key,
lalu pakai via `--elsevier-key KEY` atau `export ELSEVIER_API_KEY=KEY`.
Tanpa key, sumber Scopus/ScienceDirect otomatis di-skip (yang lain tetap jalan).

**Soal login SSO UNDIP — penting:**
- Script ini **tidak melakukan login SSO**. SSO adalah login browser
  (SAML, bisa ada MFA/captcha) yang tidak bisa & tidak aman diotomatisasi
  dari script CLI. Jangan pernah menempel password SSO ke script apa pun.
- Yang membuka full-text berbayar adalah **hak akses institusi**, yang dikenali
  dari **IP**: jaringan kampus, **VPN UNDIP**, atau proxy perpustakaan.
- Alurnya: script memberi kamu `manual_download.csv` berisi kolom **link DOI**
  (`https://doi.org/...`). Buka link itu dari **browser di jaringan
  kampus/VPN** (login SSO cukup sekali di browser), download PDF-nya.
  Kalau script-nya sendiri dijalankan dari jaringan kampus/VPN, percobaan
  download via Elsevier API juga berpeluang berhasil otomatis.

Abstract → Excel (butuh `OPENROUTER_API_KEY`):

```bash
export OPENROUTER_API_KEY=sk-or-xxxx
python abstract_to_excel.py
python abstract_to_excel.py --dir ./jurnal_download --out hasil.xlsx
python abstract_to_excel.py --dir ./jurnal_download --out hasil.xlsx --api-key sk-or-xxxx
```

## Catatan API

- Elsevier (Scopus + ScienceDirect) **wajib** API key.
  Daftar gratis: https://dev.elsevier.com
- Unpaywall butuh email valid di `-e`.
- OpenRouter: https://openrouter.ai/
