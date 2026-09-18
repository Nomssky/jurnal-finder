# Jurnal Finder

> Cari & download jurnal ilmiah secara gratis. Tanpa login, tanpa API key, boleh Bahasa Indonesia.

## Fitur

- Cari paper dari **beberapa sumber** sekaligus (OpenAlex, DOAJ, CrossRef, Unpaywall)
- **Filter bidang**: Ekonomi, Akuntansi, Manajemen, Keuangan — hasil lebih mengerucut
- **Filter penerbit**: Elsevier, Emerald, Wiley, Taylor & Francis, Springer, Oxford, Cambridge, IEEE, dll
- **Verifikasi isi PDF**: judul di halaman awal harus cocok → mencegah file salah isi
- Auto-translate Bahasa Indonesia → Inggris
- Download PDF otomatis (Open Access + Unpaywall); paper berbayar dikumpulkan di `manual_download.csv` **berisi link DOI** untuk dibuka via akses kampus
- Export hasil ke CSV
- **100% gratis**, tidak perlu daftar atau login

## Install (mudah — cukup 1 baris)

Salin **satu perintah** di bawah ini, tempel di terminal, tekan Enter.
Installer otomatis menyiapkan semua yang dibutuhkan (termasuk Python bila belum ada).

### Linux / macOS

Buka **Terminal**, tempel, Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Nomssky/jurnal-finder/main/install.sh | bash
```

### Windows

Buka **PowerShell** (klik Start → ketik "PowerShell"), tempel, Enter:

```powershell
irm https://raw.githubusercontent.com/Nomssky/jurnal-finder/main/install.ps1 | iex
```

> Belum punya PowerShell? Bisa juga: unduh repo ini (tombol **Code → Download ZIP**),
> ekstrak, lalu klik dua kali **`install.bat`**.

Setelah selesai, **tutup lalu buka terminal baru**, dan ketik `jf`.

<details>
<summary>Instalasi manual (opsional, untuk yang sudah punya Python & git)</summary>

```bash
git clone https://github.com/Nomssky/jurnal-finder.git ~/.jf
bash ~/.jf/install.sh
```

Atau jalankan installer langsung dari folder repo: `bash install.sh` (Linux/macOS)
/ `install.bat` (Windows). Installer otomatis memakai Python 3.10+ yang tersedia.

</details>

## Cara Pakai

Setelah instalasi, **buka terminal/Command Prompt baru** lalu ketik:

```bash
jf
```

Paling mudah — mode dipandu (akan ditanya topik, bidang, penerbit, dll):

```bash
jf
```

Atau lewat baris perintah:

```bash
# Bidang ekonomi (topik Bahasa Indonesia, auto-translate)
jf --topik "pengaruh inflasi terhadap harga saham" --bidang ekonomi -n 10

# Bidang akuntansi
jf --keyword-en "chatgpt adoption accounting" --bidang akuntansi

# Filter penerbit + rentang tahun
jf --topik "kecerdasan buatan di akuntansi" --bidang akuntansi --penerbit elsevier --tahun 2020 2024

# Hanya ekstrak PDF yang sudah ada (tanpa download ulang)
jf --extract-only

# Lihat semua opsi
jf --help
```

**Bidang**: `ekonomi`, `akuntansi`, `manajemen`, `keuangan`, `umum`

**Penerbit**: `elsevier`, `emerald`, `wiley`, `taylor-francis`, `springer`, `oxford`, `cambridge`, `ieee`, `asce`, `igi`, `jstor`, `sage`

## Output

Semua hasil disimpan di `~/jurnal_download/`:

```
~/jurnal_download/
├── *.pdf                    # Jurnal yang berhasil didownload & terverifikasi
├── hasil_pencarian.csv      # Daftar semua paper (No, Title, Year, DOI, Bidang, Publisher, Journal, Status, Source)
├── manual_download.csv      # Paper berbayar + link DOI (kolom "Link DOI" & "Cara ambil")
└── tabel_perbandingan.xlsx  # Hasil ekstraksi PDF (jika ada)
```

## Cara Kerja

```
Query + Bidang + (opsional) Penerbit
     ↓
OpenAlex (difilter bidang & penerbit) + DOAJ + CrossRef
     ↓
Gabung & hapus duplikat
     ↓
Download PDF:
  1. Open Access (OpenAlex/DOAJ)
  2. Unpaywall (DOI → PDF gratis)
  3. Cross-ref judul HARUS cocok (DOAJ/arXiv/CrossRef)
     ↓
Verifikasi isi PDF (judul di halaman awal harus ada)
     ↓
PDF tersimpan + laporan CSV
```

## Tentang Database Berlangganan (ScienceDirect, Scopus, Emerald, Wiley, dll)

Banyak yang bertanya apakah tool ini bisa mengambil jurnal dari database
berlangganan. Jawabannya perlu dipahami dengan jelas:

### Yang BISA dilakukan

- **Mencari metadata + DOI** dari hampir semua penerbit besar (Elsevier,
  Emerald, Wiley, Taylor & Francis, Springer, Oxford, Cambridge, IEEE, ASCE,
  IGI Global, JSTOR, SAGE, dll) lewat CrossRef & OpenAlex — ini katalog publik
  yang juga menjadi sumber data Scopus.
- **Download otomatis** PDF-nya **hanya jika versi Open Access tersedia**
  (via OpenAlex, Unpaywall, DOAJ). Sekarang banyak jurnal Elsevier/Wiley/Emerald
  yang Open Access, sehingga cukup sering berhasil.

### Yang TIDAK bisa dilakukan

- **Tidak bisa** login ke database berlangganan (ScienceDirect, Scopus, Embase,
  EBSCOhost, ProQuest, Westlaw, ClinicalKey, McGraw-Hill Access, dll) tanpa
  akun institusi Anda. Ini bukan keterbatasan tool, tapi memang sistem mereka
  mengunci akses.
- **Tidak** menggunakan layanan akses ilegal (Sci-Hub, Anna's Archive,
  Library Genesis, Z-Library, dll). Tool ini hanya memakai jalur legal.

### Cara mengambil paper berbayar dengan benar

1. Jalankan pencarian seperti biasa.
2. Buka `~/jurnal_download/manual_download.csv`.
3. Kolom **Link DOI** berisi link ke halaman resmi paper.
4. Buka link tersebut di **browser** sambil login ke **akun kampus / perpustakaan**
   Anda (atau pakai VPN kampus). PDF fulltext akan tersedia otomatis.
5. Cara ini legal, gratis (lewat langganan kampus Anda), dan didukung oleh
   semua penerbit.

Untuk melihat daftar platform yang praktis hanya berisi paper berbayar:
Scopus, Embase, EBSCOhost, ProQuest, Westlaw, ClinicalKey, McGraw-Hill Access.

## Requirements

- **Python 3.10+** — installer akan mencoba memasangnya otomatis bila belum ada
  (via Homebrew/apt/dnf/pacman di Linux-macOS, atau winget di Windows).
- Tidak perlu API key
  (opsional: set variabel `UNPAYWALL_EMAIL` agar lookup Unpaywall lebih optimal)

## Uninstall

Hapus folder `~/.jf` (`%USERPROFILE%\.jf` di Windows) dan file perintah
`~/.local/bin/jf`. Hasil download ada di `~/jurnal_download/` (hapus bila tidak perlu).

## License

MIT
