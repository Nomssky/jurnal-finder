# Problem & Status Integrasi Sumber Jurnal

Tanggal: 2026-09-17

## Sumber yang sudah terintegrasi

| Sumber | Status | Keterangan |
|---|---|---|
| OpenAlex | ✅ Aktif | Gratis, tanpa API key, ~84M articles |
| Unpaywall | ✅ Aktif | Gratis, perlu email, cari PDF gratis dari DOI |
| ScienceDirect (SSO) | ✅ Aktif | Login sekali via Playwright, download via session cookies |

## Sumber yang ingin ditambahkan

| Sumber | Status | Masalah |
|---|---|---|
| Anna's Archive | ❌ Terblokir | DDoS-Guard: semua HTTP request kena 403 |
| Sci-Hub | ❌ Terblokir | Robot check: JavaScript challenge |
| DOAJ | ✅ Aktif | API publik gratis, OJS PDF extraction jalan (2/3 berhasil) |

## Detail Masalah: Anti-Bot Protection

### Anna's Archive
- Domain aktif: `annas-archive.gd`, `annas-archive.pk`, `annas-archive.gl`
- Search endpoint: `https://annas-archive.gd/search?q=...`
- SciDB (DOI lookup): `https://annas-archive.gd/scidb/{doi}/`
- **DDoS-Guard** memblokir:
  - `curl` → 403
  - `requests` → 403
  - `cloudscraper` → 403
  - `curl_cffi` (impersonate Chrome) → 403
  - `Playwright Chromium` (headless & non-headless) → 403
  - `Playwright Firefox` (headless & non-headless) → 403
- DDoS-Guard mendeteksi fingerprint browser (TLS, HTTP/2, JavaScript challenge)
- Tidak ada API publik yang bisa diakses tanpa browser asli

### Sci-Hub
- Domain aktif: `sci-hub.ru`, `sci-hub.ren`
- URL pattern: `https://sci-hub.ru/{doi}`
- **Robot check** memblokir:
  - `curl` → page "are you a robot?"
  - `curl_cffi` → page "are you a robot?" (title muncul tapi body kosong)
  - `cloudscraper` → page "are you a robot?"
- Halaman robot check menggunakan JavaScript challenge yang hanya bisa diselesaikan di browser asli

### Percobaan yang sudah dilakukan
1. `curl` ke `.gl`, `.gs`, `.li`, `.cc` → 403 / redirect ke domain parkir
2. `cloudscraper` → 403
3. `curl_cffi` dengan `impersonate='chrome'` → 403
4. `Playwright Chromium headless/non-headless` → 403
5. `Playwright Firefox headless/non-headless` → 403
6. `nodriver` → SyntaxError di Python 3.14
7. `undetected-chromedriver` → install timeout
8. `DrissionPage` → install timeout

### Kesimpulan
**Satu-satunya cara gratis** untuk bypass DDoS-Guard/robot check:
- Pakai **browser Firefox yang sudah jalan** dengan `--remote-debugging-port=9222`
- Atau pakai **CAPTCHA solving service** (berbayar: ~$0.50-3.00/1000 CAPTCHA)

## Download Pipeline Saat Ini

```
Paper dari OpenAlex + DOAJ
  ↓
1. OpenAlex/DOAJ PDF URL (open access) → download langsung
  ↓ gagal
2. Unpaywall (cari PDF gratis via DOI) → download langsung
  ↓ gagal
3. SSO Kampus (ScienceDirect via session cookies) → download
  ↓ gagal
4. ??? (Anna's Archive / Sci-Hub — terblokir DDoS-Guard)
  ↓ gagal
5. Manual: masuk manual_download.csv dengan link DOI
```

### Target
Hilangkan langkah 5 (manual) dengan menambah sumber yang bisa diakses otomatis.

## Opsi Solusi

| Opsi | Gratis? | Otomatis? | Keterangan |
|---|---|---|---|
| Firefox remote-debugging | ✅ | ⚠️ Semi | Perlu user buka Firefox dengan flag, CAPTCHA tetap manual |
| CAPTCHA solving API | ❌ | ✅ | 2Captcha/AntiCaptcha, biaya kecil |
| DOAJ (open access journals) | ✅ | ✅ | Hanya journal open access, tapi legitimasi tinggi |
| Sci-Hub datasets (torrent) | ✅ | ⚠️ | Database ~94TB, terlalu besar untuk个人 |
| Tor proxy | ✅ | ⚠️ | Belum diuji, mungkin bisa bypass |

## Rencana Selanjutnya
1. Integrasi DOAJ sebagai sumber tambahan (open access journals)
2. Evaluasi apakah ada mirror Anna's Archive / Sci-Hub yang tidak pakai DDoS-Guard
3. Pertimbangkan remote-debugging Firefox sebagai opsi semi-otomatis
