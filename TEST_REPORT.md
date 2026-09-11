# Laporan Test & Root Cause — Jurnal Finder

Tanggal: 2026-09-11
Penguji: Otomatis (fungsional + live API)
File yang diuji: `journal_dl.py` (371 baris), `abstract_to_excel.py` (322 baris), `requirements.txt`

## Ringkasan hasil

| Fitur | Status | Keterangan |
|---|---|---|
| `abstract_to_excel.py --help` | ✅ BISA | argparse jalan |
| `extract_pdf_text` (pdftotext → pypdf → pdfminer) | ✅ BISA | 4000 chars dari PDF asli `jurnal_download1/` |
| `parse_with_deepseek` tanpa API key | ✅ BISA (fallback) | Kembali `_fallback_entry`, tidak crash |
| `build_excel` | ✅ BISA | XLSX valid, 2 sheet (Tabel + Gap X), 6514 bytes untuk 2 entri |
| Guard folder kosong / PDF korup | ✅ BISA | Pesan error rapi, tidak crash |
| `journal_dl.safe_filename` normal | ✅ BISA | Sanitasi `A: B/C?` → `A_ B_C_` benar |
| `journal_dl.download_pdf` PDF valid | ✅ BISA | Magic bytes `%PDF` divalidasi |
| `download_pdf` URL HTML | ✅ BISA (ditolak) | Return `False`, file sampah dihapus |
| `get_free_pdf_url(None/"")` | ✅ BISA | Return `None` |
| `run()` export CSV + dedup + guard kosong | ✅ BISA | Diuji dengan mock, dedup `paperId` jalan |
| `journal_dl.py -k/--help` (mode CLI) | ❌ GAGAL | Selalu masuk `interactive()`, argumen diabaikan |
| `search_papers` live tanpa API key | ❌ GAGAL (rate limit) | `429 Too Many Requests` bahkan untuk `limit=2` |
| Fresh install `pip install -r requirements.txt` | ❌ GAGAL | `openpyxl`, `pypdf` tidak dideklarasikan |
| `safe_filename("", None)` | ❌ BUG KECIL | Hasil `".pdf"` |
| Push ke GitHub | ⬜ BELUM | Belum ada git repo, `gh` CLI tidak ada |

## Root cause detail

### 1. [KRITIS] Entry-point CLI mati — `journal_dl.py:370-371`
```python
if __name__ == "__main__":
    interactive()
```
`main()` (yang berisi `argparse` untuk `-k/-n/-y/-e/--api-key`) **tidak pernah dipanggil**.
Akibatnya `python journal_dl.py -k "ESG" -n 20` / `--help` tetap memanggil
`input()`, lalu `EOFError: EOF when reading a line` di environment non-interaktif.
Bukti: `.venv/bin/python journal_dl.py --help` → masuk banner interactive, bukan usage.

### 2. [KRITIS] `requirements.txt` tidak lengkap
Isi hanya `requests>=2.31.0`, padahal:
- `abstract_to_excel.py` → `openpyxl` (wajib), `pypdf` + `pdfminer` (fallback extract)
- `journal_dl.py` → `requests` saja (OK)
- Cek `.venv`: `openpyxl 3.1.5`, `pypdf 6.13.2` terinstall tapi tak tercatat;
  `pdfminer` tidak ada sama sekali → cabang fallback ketiga mati diam-diam.
Clone baru + `pip install -r requirements.txt` → `ModuleNotFoundError: openpyxl`.

### 3. [SEDANG] Semantic Scholar rate-limit tanpa API key
`curl` langsung ke `api.semanticscholar.org/graph/v1/paper/search?limit=2` → `429`.
Retry di `search_papers()` memakai `15 * (2**attempt)` = 15s/30s/60s/120s/240s
(total bisa ±8 menit per keyword) + `time.sleep(5)` antar keyword.
Tanpa `S2_API_KEY`, di IP bersama script terlihat "hang" (test kami timeout 120 detik).
`S2_API_KEY` hanya bisa diisi via `--api-key` yang mati karena bug #1;
mode `interactive()` tidak pernah menanyakan API key.

### 4. [KECIL] `safe_filename` judul kosong → `".pdf"` (`journal_dl.py:128-134`)
Tidak ada guard `if not name`. Judul kosong dari API menghasilkan file `".pdf"`
(hidden file di Linux) dan rawan tabrakan overwrite (judul sama + tahun sama
→ nama file identik, file lama ditimpa tanpa peringatan).

### 5. [KECIL] `download_pdf` menelan error (`journal_dl.py:101-125`)
`except Exception: return False` tanpa log; blok cek `Content-Type` mati
(`pass` di kedua cabang); tidak ada proteksi tabrakan nama file.

### 6. [INFO] `abstract_to_excel` butuh API key, tanpa mode offline
Tanpa `OPENROUTER_API_KEY` script langsung `return` sebelum membaca PDF,
padahal `_fallback_entry()` sudah ada. Untuk repo publik perlu dokumentasi
+ contoh `.env`, dan (opsional) flag `--no-ai` agar tetap bisa generate Excel
berisi judul file.

### 7. [INFO] Kebersihan repo untuk GitHub
Belum `git init`, belum `.gitignore` (bahaya ke-commit: `.venv/`,
`*.pdf`, `*.xlsx`, `*.csv`, `__pycache__/` — folder `jurnal_download1/` saja
±5 MB), belum `README.md`, `gh` CLI tidak terinstall sehingga push butuh
token/manual remote.

## Perbaikan yang dilakukan
1. `journal_dl.py`: dispatch `main()` bila ada argv, `interactive()` bila tidak.
2. `requirements.txt`: tambah `openpyxl`, `pypdf`, `pdfminer.six`.
3. `journal_dl.safe_filename`: fallback `"untitled"` bila judul kosong.
4. Tambah `.gitignore` + `README.md` agar aman di-push ke repo publik.
5. Verifikasi ulang: `--help` CLI, compile, smoke test Excel & download.

## Cara verifikasi ulang
```bash
python -m pip install -r requirements.txt
python journal_dl.py --help
python abstract_to_excel.py --help
python abstract_to_excel.py --dir ./jurnal_download --out hasil.xlsx --api-key sk-or-xxxx
```
