# Jurnal Finder

> Cari & download jurnal ilmiah secara gratis. Tanpa auth, tanpa login, tanpa API key.

## Features

- Cari paper dari **4 sumber** sekaligus (OpenAlex, DOAJ, arXiv, CrossRef)
- Auto-translate Bahasa Indonesia → Inggris
- Download PDF otomatis (termasuk preprint dari arXiv)
- Export hasil ke CSV
- **100% gratis**, tidak perlu daftar atau login

## Install

### Linux / macOS

```bash
git clone <repo-url> ~/.jf && bash ~/.jf/install.sh
```

Atau kalau repo sudah ada di folder lain:

```bash
bash install.sh <repo-url>   # opsional: clone/update dari remote
```

### Windows

```cmd
git clone <repo-url> %USERPROFILE%\.jf
install.bat
```

## Usage

```bash
# Keyword Inggris langsung
jf --keyword-en "machine learning" -n 10

# Bahasa Indonesia (auto-translate)
jf --topik "pengaruh inflasi terhadap harga saham" -n 10

# Filter tahun
jf --keyword-en "deep learning" --tahun 2020 2024

# Hanya ekstrak PDF yang sudah ada (tanpa download ulang)
jf --extract-only

# Mode interaktif
jf
```

## Output

Semua hasil disimpan di `~/jurnal_download/`:

```
~/jurnal_download/
├── *.pdf                    # Jurnal yang berhasil didownload
├── hasil_pencarian.csv      # Daftar semua paper
├── manual_download.csv      # Paper yang perlu manual (jika ada)
└── tabel_perbandingan.xlsx  # Hasil ekstraksi PDF (jika ada)
```

## How it works

```
Query → OpenAlex + DOAJ + arXiv + CrossRef
         ↓
    Search & deduplicate
         ↓
    Download PDF (OA links)
         ↓
    Cross-ref by title (arXiv/DOAJ)
         ↓
    PDF saved + CSV report
```

## Requirements

- Python 3.10+
- Tidak perlu API key

## License

MIT
