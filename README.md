# Jurnal Finder — 1 Tool: Cari → Download → Analisis

Satu script (`jurnal_finder.py`) untuk seluruh alur jurnal skripsi.
Boleh input **Bahasa Indonesia** — otomatis diterjemahkan gratis.

## Alur

1. **Ceritakan maumu** — topik / judul / variabel X / Y (Indonesia OK)
2. **Translate otomatis** ke Inggris (MyMemory, gratis tanpa daftar;
   ada kamus offline bila internet/API gagal; keyword bisa diedit manual)
3. **Login SSO kampus sekali** via browser (kamu ketik password sendiri —
   script hanya menyimpan cookie sesi, bukan password)
4. **Cari + download massal** — OpenAlex (gratis tanpa key, meliput artikel
   yang sama terindeks di Scopus/ScienceDirect) → PDF gratis → sesi kampus
   → sisa paywall masuk `manual_download.csv` berisi link DOI
5. **Pilihan ekstrak** — jadikan `tabel_perbandingan.xlsx`:
   tanpa key = tabel metadata; dengan OpenRouter key (gratis) = analisis AI
   (X/Y/metode/hasil/teori/sampel + sheet gap analisis)

## Instalasi

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # sekali saja, untuk login SSO
# Opsional: sudo apt install poppler-utils (ekstrak PDF lebih akurat)
```

## Pemakaian

```bash
python jurnal_finder.py
python jurnal_finder.py --topik "pengaruh inflasi terhadap harga saham" --x inflasi --y "harga saham" -n 10
python jurnal_finder.py --keyword-en "inflation stock prices" --skip-login --no-extract
```

Hasil ada di `./jurnal_download/` (`hasil_pencarian.csv`,
`manual_download.csv`, PDF, `tabel_perbandingan.xlsx`).

## Catatan akses

- Tahap cari + translate + PDF gratis: **tanpa key, tanpa login apa pun**.
- PDF paywall: dibuka lewat **sesi SSO** (login sekali di browser) atau
  manual via link DOI dari jaringan kampus/VPN.
- File sesi (`.session_*.json`) itu rahasia — sudah di-`.gitignore`,
  jangan pernah di-commit/upload.
- Riwayat pengujian ada di [`TEST_REPORT.md`](TEST_REPORT.md) (arsip versi lama).
