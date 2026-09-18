# Jurnal Finder

> Cari & download jurnal ilmiah secara gratis. Tanpa auth, tanpa login, tanpa API key.

## Features

- Cari paper dari **beberapa sumber** sekaligus (OpenAlex, DOAJ, CrossRef, Unpaywall)
- **Filter bidang**: Ekonomi, Akuntansi, Manajemen, Keuangan — hasil lebih mengerucut
- **Verifikasi isi PDF**: judul di halaman awal harus cocok → mencegah file salah isi
- Auto-translate Bahasa Indonesia → Inggris
- Download PDF otomatis (Open Access + Unpaywall), sisanya ditandai untuk akses kampus
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
# Bidang ekonomi, topik Bahasa Indonesia (auto-translate)
jf --topik "pengaruh inflasi terhadap harga saham" --bidang ekonomi -n 10

# Bidang akuntansi
jf --keyword-en "chatgpt adoption accounting" --bidang akuntansi

# Filter tahun
jf --keyword-en "deep learning" --bidang manajemen --tahun 2020 2024

# Hanya ekstrak PDF yang sudah ada (tanpa download ulang)
jf --extract-only

# Mode interaktif (dipandu, akan ditanya bidang)
jf
```

Bidang yang tersedia: `ekonomi`, `akuntansi`, `manajemen`, `keuangan`, `umum`.

## Output

Semua hasil disimpan di `~/jurnal_download/`:

```
~/jurnal_download/
├── *.pdf                    # Jurnal yang berhasil didownload & terverifikasi
├── hasil_pencarian.csv      # Daftar semua paper (termasuk kolom Bidang & Journal)
├── manual_download.csv      # Paper paywalled (link DOI untuk akses kampus)
└── tabel_perbandingan.xlsx  # Hasil ekstraksi PDF (jika ada)
```

## How it works

```
Query + Bidang
     ↓
OpenAlex (difilter bidang) + DOAJ + CrossRef
     ↓
Search & deduplicate
     ↓
Download PDF:
  1. Open Access (OpenAlex/DOAJ)
  2. Unpaywall (DOI → PDF gratis)
  3. Cross-ref judul HARUS cocok (DOAJ/arXiv/CrossRef)
     ↓
Verifikasi isi PDF (judul di halaman awal harus ada)
     ↓
PDF tersimpan + CSV report
```

## Sumber berlangganan (ScienceDirect, Scopus, Emerald, Wiley, dll)

Database seperti ScienceDirect, Scopus, Emerald, Wiley, Taylor & Francis, JSTOR,
IEEE **tidak bisa di-scrape otomatis** tanpa langganan/akses kampus. Tool ini:

1. Mengambil metadata + DOI dari sumber tersebut via CrossRef/OpenAlex
2. Mencoba cari versi PDF gratis via OpenAlex/Unpaywall/DOAJ
3. Paper yang tetap paywalled masuk `manual_download.csv` (lengkap dengan link DOI)

Untuk mendownload yang paywalled, gunakan **akses kampus/institusi** Anda dengan
membuka link DOI di `manual_download.csv`.

## Requirements

- Python 3.10+
- Tidak perlu API key (opsional: set `UNPAYWALL_EMAIL` untuk lookup Unpaywall)

## License

MIT
