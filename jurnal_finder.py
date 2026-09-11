#!/usr/bin/env python3
"""
jurnal_finder.py - SATU tool untuk cari + download + analisis jurnal skripsi.

Alur (dipandu, boleh Bahasa Indonesia):
  1. Ceritakan topik / judul / variabel  → otomatis diterjemahkan ke Inggris (gratis)
  2. Login SSO kampus SEKALI via browser → sesi dipakai untuk download PDF paywall
  3. Tool mencari (OpenAlex, gratis tanpa key) + download semua yang bisa
  4. Pilihan: ekstrak semua PDF jadi tabel Excel analisis perbandingan

Yang TIDAK disimpan tool ini: password SSO (kamu ketik sendiri di browser),
API key apa pun untuk tahap 1-3 (semuanya gratis tanpa daftar).

Pakai:
  python jurnal_finder.py            # mode dipandu (disarankan)
  python jurnal_finder.py --help     # mode CLI
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────
OPENALEX_API   = "https://api.openalex.org/works"
MYMEMORY_API   = "https://api.mymemory.translated.net/get"
UNPAYWALL_API  = "https://api.unpaywall.org/v2/{doi}"
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"

SESSION_FILE = Path("./.session_sciencedirect.json")
LOGIN_URL    = "https://www.sciencedirect.com/"
DOWNLOAD_DIR = Path("./jurnal_download")

OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY", "")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ── Colors ─────────────────────────────────────────────────────────────────
class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def ok(msg):    print(f"{C.GREEN}✓{C.RESET} {msg}")
def warn(msg):  print(f"{C.YELLOW}⚠{C.RESET} {msg}")
def err(msg):   print(f"{C.RED}✗{C.RESET} {msg}")
def info(msg):  print(f"{C.CYAN}→{C.RESET} {msg}")
def bold(msg):  print(f"{C.BOLD}{msg}{C.RESET}")

# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 1 — Translate Indonesia → Inggris (gratis: MyMemory + kamus fallback)
# ═══════════════════════════════════════════════════════════════════════════
ID_MARKERS = {
    "yang", "dan", "atau", "dengan", "terhadap", "pengaruh", "pada", "dari",
    "untuk", "dalam", "adalah", "sebuah", "tentang", "bagaimana", "apakah",
    "harga", "saham", "perusahaan", "nilai", "kinerja", "keuangan", "studi",
    "kasus", "serta", "antara", "oleh", "karena", "jika", "tahun", "analisis",
}

# (frasa Indonesia, padanan Inggris) — dipakai hanya jika API translate gagal
ACADEMIC_DICT = [
    ("bursa efek indonesia", "indonesia stock exchange"),
    ("yang terdaftar di", "listed on"),
    ("nilai perusahaan", "firm value"),
    ("harga saham", "stock prices"),
    ("kinerja keuangan", "financial performance"),
    ("laporan keuangan", "financial statements"),
    ("ukuran perusahaan", "firm size"),
    ("studi empiris", "empirical study"),
    ("terhadap", "on"),
    ("pengaruh", "effect of"),
    ("profitabilitas", "profitability"),
    ("likuiditas", "liquidity"),
    ("leverage", "leverage"),
    ("pertumbuhan", "growth"),
    ("inflasi", "inflation"),
    ("strategi", "strategy"),
    ("perdagangan", "trading"),
    ("saluran", "channel"),
    ("terobosan", "breakout"),
    ("penembusan", "breakout"),
    ("donchian", "donchian"),
]

def looks_indonesian(text: str) -> bool:
    words = {w.strip(".,!?;:()\"'").lower() for w in (text or "").split()}
    return len(words & ID_MARKERS) > 0

def dict_translate(text: str) -> str:
    out = text or ""
    for id_phrase, en in sorted(ACADEMIC_DICT, key=lambda x: -len(x[0])):
        out = _replace_ci(out, id_phrase, en)
    return " ".join(out.split())

def _replace_ci(text: str, old: str, new: str) -> str:
    import re
    return re.sub(re.escape(old), new, text, flags=re.IGNORECASE)

def translate_id_en(text: str) -> tuple[str, str]:
    """Return (hasil_inggris, metode): metode = 'asli' | 'mymemory' | 'kamus'."""
    text = (text or "").strip()
    if not text:
        return "", "asli"
    if not looks_indonesian(text):
        return text, "asli"  # sudah Inggris (atau bukan Indonesia) → pakai apa adanya
    try:
        resp = requests.get(MYMEMORY_API, params={"q": text, "langpair": "id|en"},
                            headers=HEADERS, timeout=15)
        data = resp.json()
        hasil = ((data or {}).get("responseData") or {}).get("translatedText", "").strip()
        if data.get("responseStatus") == 200 and hasil and not data.get("quotaFinished"):
            return hasil, "mymemory"
    except Exception:
        pass
    warn("Translate online gagal → pakai kamus offline (hasil bisa kurang rapi).")
    return dict_translate(text), "kamus"

# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 2 — Cari jurnal (OpenAlex: gratis, tanpa API key)
# Meliput artikel yang sama terindeks di Scopus/ScienceDirect (lengkap dgn DOI).
# ═══════════════════════════════════════════════════════════════════════════
def norm_openalex(w: dict) -> dict:
    doi_raw = w.get("doi") or ""
    doi = doi_raw.replace("https://doi.org/", "").strip() or None
    authors = [{"name": a.get("author", {}).get("display_name", "?")}
               for a in (w.get("authorships") or [])[:3]]
    oa = w.get("open_access") or {}
    loc = w.get("primary_location") or {}
    boa = w.get("best_oa_location") or {}
    pdf_url = loc.get("pdf_url") or boa.get("pdf_url") or oa.get("oa_url")
    src = (loc.get("source") or {}).get("display_name") or "-"
    pid = f"doi:{doi.lower()}" if doi else w.get("id", "")
    return {
        "paperId": pid, "title": w.get("title") or "Untitled", "authors": authors,
        "year": w.get("publication_year"), "externalIds": {"DOI": doi} if doi else {},
        "citationCount": w.get("cited_by_count", 0) or 0,
        "openAccessPdf": {"url": pdf_url} if pdf_url else None,
        "journal": src,
    }

def search_openalex(query: str, limit: int = 20,
                    year_start: int = None, year_end: int = None,
                    email: str = "") -> list:
    info(f"Mencari: '{query}' ...")
    params = {"search": query, "per-page": min(limit, 200),
              "sort": "cited_by_count:desc", "select": ",".join([
                  "id", "doi", "title", "publication_year", "authorships",
                  "cited_by_count", "open_access", "primary_location",
                  "best_oa_location"])}
    if email:
        params["mailto"] = email
    filters = []
    if year_start:
        filters.append(f"from_publication_date:{year_start}-01-01")
    if year_end:
        filters.append(f"to_publication_date:{year_end}-12-31")
    if filters:
        params["filter"] = ",".join(filters)
    for attempt in range(3):
        try:
            resp = requests.get(OPENALEX_API, params=params, headers=HEADERS, timeout=25)
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                warn(f"OpenAlex rate limit, tunggu {wait}s... ({attempt+1}/3)")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                err(f"OpenAlex HTTP {resp.status_code} untuk '{query}'")
                return []
            papers = [norm_openalex(w) for w in resp.json().get("results", [])]
            ok(f"Ditemukan {len(papers)} paper")
            return papers
        except requests.exceptions.RequestException as e:
            err(f"Gagal search: {e}")
            return []
    return []

# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 3 — Login SSO (browser) + download
# ═══════════════════════════════════════════════════════════════════════════
def load_session() -> requests.Session | None:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    session = requests.Session()
    session.headers.update(HEADERS)
    for c in data.get("cookies", []):
        try:
            session.cookies.set(c["name"], c.get("value", ""),
                                domain=c.get("domain", ""), path=c.get("path", "/"))
        except Exception:
            continue
    return session if session.cookies else None

def looks_like_login_wall(resp: requests.Response) -> bool:
    url = (getattr(resp, "url", "") or "").lower()
    if resp.status_code in (401, 403):
        return True
    return any(m in url for m in ("login", "signin", "sign-in", "sso", "shibboleth", "authenticate"))

def cmd_login():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        err("playwright belum terinstall. Jalankan:")
        err("  pip install -r requirements.txt && python -m playwright install chromium")
        sys.exit(1)
    bold("\n═══════════════════════════════════════")
    bold("  🔑 Login kampus (sekali saja)")
    bold("═══════════════════════════════════════\n")
    print("Browser akan terbuka. Langkah kamu:")
    print("  1. Klik Sign in → Sign in via your institution → cari UNDIP")
    print("  2. Login SSO seperti biasa (kamu yang ketik password sendiri)")
    print("  3. Pastikan halaman terbuka sebagai user institusi")
    print("  4. Kembali ke sini, tekan ENTER\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        ctx.new_page().goto(LOGIN_URL, wait_until="domcontentloaded")
        input("Kalau sudah login di browser, tekan ENTER di sini... ")
        ctx.storage_state(path=str(SESSION_FILE))
        browser.close()
    if load_session():
        ok(f"Sesi tersimpan di {SESSION_FILE} — JANGAN upload/commit file ini.")
    else:
        err("Gagal menyimpan sesi (tidak ada cookie). Ulangi login.")

def get_free_pdf_url(doi: str, email: str) -> str | None:
    if not doi:
        return None
    try:
        resp = requests.get(UNPAYWALL_API.format(doi=doi),
                            params={"email": email}, timeout=10)
        if resp.status_code == 200 and resp.json().get("is_oa"):
            best = resp.json().get("best_oa_location", {})
            return best.get("url_for_pdf") or best.get("url")
    except Exception:
        pass
    return None

def download_pdf(url: str, session: requests.Session | None, filepath: Path) -> str:
    """Return 'ok' | 'login' | 'fail'."""
    try:
        getter = session.get if session else requests.get
        kwargs = dict(timeout=60, stream=True)
        if session is None:
            kwargs["headers"] = HEADERS
        resp = getter(url, **kwargs)
    except requests.exceptions.RequestException:
        return "fail"
    if looks_like_login_wall(resp):
        return "login"
    try:
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        with open(filepath, "rb") as f:
            valid = f.read(4) == b"%PDF"
        if not valid:
            filepath.unlink(missing_ok=True)
            return "fail"
        return "ok"
    except Exception:
        filepath.unlink(missing_ok=True)
        return "fail"

def resolve_sd_pdf_url(doi: str, session: requests.Session) -> tuple[str | None, str]:
    """Ikuti DOI; kalau mendarat di artikel ScienceDirect → URL PDF. Status: ok|login|nonsd|error."""
    try:
        resp = session.get(f"https://doi.org/{doi}", timeout=30, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        return None, f"error: {e}"
    if looks_like_login_wall(resp):
        return None, "login"
    final = (getattr(resp, "url", "") or "").split("?")[0].rstrip("/")
    if "sciencedirect.com/science/article/pii/" not in final:
        return None, "nonsd"
    return final + "/pdfft?isDTMRedir=true&download=true", "ok"

def safe_filename(title: str, year=None, max_len: int = 80) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")
    name = "".join(c if c in keep else "_" for c in (title or ""))
    name = name[:max_len].strip() or "untitled"
    return (f"[{year}] {name}" if year else name) + ".pdf"

def run_search_download(queries: list[str], limit: int, year_start: int, year_end: int,
                        email: str, session: requests.Session | None, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    all_papers, seen = [], set()
    for kw in queries:
        for p in search_openalex(kw, limit=limit, year_start=year_start,
                                 year_end=year_end, email=email):
            key = (p.get("externalIds") or {}).get("DOI", "") or p.get("paperId")
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)
        time.sleep(1)
    bold(f"\nTotal unik: {len(all_papers)} paper\n")
    results, manual, ndone = [], [], 0
    expired = False
    for i, paper in enumerate(all_papers, 1):
        title   = paper.get("title", "Untitled")
        year    = paper.get("year")
        authors = ", ".join(a["name"] for a in paper.get("authors", [])[:3])
        doi     = (paper.get("externalIds") or {}).get("DOI")
        print(f"[{i}/{len(all_papers)}] {title[:70]}...")
        status, source = "❌ Manual", "-"
        pdf_url = (paper.get("openAccessPdf") or {}).get("url")
        if pdf_url:
            source = "Open Access"
        elif doi:
            pdf_url = get_free_pdf_url(doi, email)
            source = "Unpaywall"
        if pdf_url:
            if download_pdf(pdf_url, None, outdir / safe_filename(title, year)) == "ok":
                ok("Downloaded (gratis)"); status, ndone = "✅ Downloaded", ndone + 1
            else:
                time.sleep(5)  # publisher kadang throttle → coba sekali lagi
                if download_pdf(pdf_url, None, outdir / safe_filename(title, year)) == "ok":
                    ok("Downloaded (gratis)"); status, ndone = "✅ Downloaded", ndone + 1
                else:
                    warn("URL gratis gagal" + (" → coba sesi kampus" if session else ""))
                    pdf_url = None
        if status != "✅ Downloaded" and doi and session:
            sd_url, st = resolve_sd_pdf_url(doi, session)
            if st == "login":
                err("Sesi kampus habis → yang sisa masuk list manual.")
                expired = True
            elif st == "ok":
                dl = download_pdf(sd_url, session, outdir / safe_filename(title, year))
                if dl == "ok":
                    ok("Downloaded (akses kampus)"); status, source = "✅ Downloaded", "Kampus (SSO)"
                    ndone += 1
                elif dl == "login":
                    err("Sesi kampus habis → yang sisa masuk list manual.")
                    expired = True
        if status != "✅ Downloaded":
            manual.append({"title": title, "doi": doi or "-",
                           "year": year, "link": f"https://doi.org/{doi}" if doi else "-"})
        results.append({"No": i, "Title": title, "Authors": authors, "Year": year,
                        "DOI": doi or "-", "Citations": paper.get("citationCount", 0),
                        "Status": status, "Source": source if "Downloaded" in status else "-"})
        if expired:
            # paper sisa tetap dicatat sebagai manual
            for j, paper2 in enumerate(all_papers[i:], i + 1):
                d2 = (paper2.get("externalIds") or {}).get("DOI")
                manual.append({"title": paper2.get("title", "Untitled"), "doi": d2 or "-",
                               "year": paper2.get("year"),
                               "link": f"https://doi.org/{d2}" if d2 else "-"})
                results.append({"No": j, "Title": paper2.get("title", "Untitled"),
                                "Authors": ", ".join(a["name"] for a in paper2.get("authors", [])[:3]),
                                "Year": paper2.get("year"), "DOI": d2 or "-",
                                "Citations": paper2.get("citationCount", 0),
                                "Status": "❌ Manual", "Source": "-"})
            break
    if results:
        with open(outdir / "hasil_pencarian.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader(); w.writerows(results)
    if manual:
        with open(outdir / "manual_download.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["title", "doi", "year", "link"])
            w.writeheader(); w.writerows(manual)
    bold("\n═══════════════════════════════════════")
    bold("  SELESAI!")
    bold("═══════════════════════════════════════")
    ok(f"Berhasil download : {ndone} PDF")
    warn(f"Perlu manual      : {len(manual)} paper")
    info(f"Semua hasil CSV   : {outdir}/hasil_pencarian.csv")
    if manual:
        info(f"List manual (+link): {outdir}/manual_download.csv")
    return outdir

# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 4 — Ekstrak semua PDF jadi tabel Excel analisis (opsional)
# ═══════════════════════════════════════════════════════════════════════════
def extract_pdf_text(pdf_path: Path, max_chars: int = 4000) -> str:
    try:
        import subprocess
        r = subprocess.run(["pdftotext", "-f", "1", "-l", "3", str(pdf_path), "-"],
                           capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            return r.stdout.strip()[:max_chars]
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        text = ""
        for page in PdfReader(str(pdf_path)).pages[:3]:
            text += page.extract_text() or ""
            if len(text) >= max_chars:
                break
        if text.strip():
            return text[:max_chars]
    except Exception:
        pass
    return ""

def fallback_entry(filename: str) -> dict:
    return {"judul": filename, "penulis": "-", "tahun": "-", "jurnal": "-",
            "variabel_x": "-", "variabel_y": "-", "variabel_kontrol": "-",
            "metode": "-", "hasil": "-", "teori": "-", "sampel": "-"}

def parse_with_ai(text: str, filename: str) -> dict:
    import json as _json
    if not OPENROUTER_KEY:
        return fallback_entry(filename)
    prompt = f"""Kamu research assistant. Teks jurnal (hal 1-3):

FILENAME: {filename}
---
{text}
---

Extract JSON (tidak ditemukan = "-"). Istilah teknis boleh Inggris, penjelasan Indonesia:
{{"judul": "...", "penulis": "maks 3 nama", "tahun": "angka saja",
"jurnal": "...", "variabel_x": "...", "variabel_y": "...",
"variabel_kontrol": "...", "metode": "...", "hasil": "...",
"teori": "...", "sampel": "..."}}
Balas HANYA JSON valid."""
    try:
        resp = requests.post(
            OPENROUTER_API, timeout=60,
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                     "Content-Type": "application/json"},
            json={"model": OPENROUTER_MODEL, "max_tokens": 1000, "temperature": 0.1,
                  "messages": [{"role": "user", "content": prompt}]})
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return _json.loads(raw.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        warn(f"AI gagal untuk {filename[:40]} ({e}) → baris metadata saja.")
        return fallback_entry(filename)

def build_excel(entries: list, output_path: Path, ai_mode: bool):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook(); ws = wb.active; ws.title = "Tabel Jurnal"
    hdr_fill = PatternFill("solid", start_color="1F4E79")
    alt_fill = PatternFill("solid", start_color="EBF3FB")
    wht_fill = PatternFill("solid", start_color="FFFFFF")
    sub_fill = PatternFill("solid", start_color="2E75B6")
    hdr_font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    sub_font = Font(name="Arial", bold=True, color="FFFFFF", size=9)
    body_font = Font(name="Arial", size=9)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_wrap = Alignment(horizontal="left", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.merge_cells("A1:K1")
    ws["A1"] = "TABEL PERBANDINGAN LITERATUR" + (" (AI)" if ai_mode else " (METADATA)")
    ws["A1"].font = Font(name="Arial", bold=True, size=12, color="1F4E79")
    ws["A1"].alignment = center; ws.row_dimensions[1].height = 24
    ws.merge_cells("A2:K2")
    ws["A2"] = f"Total: {len(entries)} jurnal"
    ws["A2"].font = Font(name="Arial", size=9, italic=True, color="595959")
    ws["A2"].alignment = center; ws.row_dimensions[2].height = 16
    cols = [("No", 5), ("Judul", 38), ("Penulis", 18), ("Tahun", 7), ("Jurnal", 20),
            ("Variabel X", 22), ("Variabel Y", 18), ("Kontrol", 18), ("Metode", 18),
            ("Hasil / Temuan", 28), ("Teori & Sampel", 22)]
    ws.row_dimensions[3].height = 28
    for col, (label, width) in enumerate(cols, 1):
        cell = ws.cell(row=3, column=col, value=label)
        cell.font = hdr_font; cell.fill = hdr_fill
        cell.alignment = center; cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = width
    for i, e in enumerate(entries, 1):
        row = i + 3
        fill = alt_fill if i % 2 == 0 else wht_fill
        teori_sampel = "\n".join(s for s in [e.get("teori", "-"), e.get("sampel", "-")] if s != "-") or "-"
        values = [i, e.get("judul", "-"), e.get("penulis", "-"), e.get("tahun", "-"),
                  e.get("jurnal", "-"), e.get("variabel_x", "-"), e.get("variabel_y", "-"),
                  e.get("variabel_kontrol", "-"), e.get("metode", "-"),
                  e.get("hasil", "-"), teori_sampel]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.font = body_font; cell.fill = fill; cell.border = border
            cell.alignment = center if col in (1, 4) else left_wrap
        ws.row_dimensions[row].height = 60
    ws.freeze_panes = "B4"
    if ai_mode:
        ws2 = wb.create_sheet("Analisis Gap X")
        ws2["A1"] = "ANALISIS VARIABEL X — FREKUENSI & GAP PENELITIAN"
        ws2["A1"].font = Font(name="Arial", bold=True, size=11, color="1F4E79")
        for col, h in enumerate(["Variabel X", "Jumlah Jurnal", "Catatan"], 1):
            cell = ws2.cell(row=2, column=col, value=h)
            cell.font = sub_font; cell.fill = sub_fill
            cell.alignment = center; cell.border = border
        ws2.column_dimensions["A"].width = 35
        ws2.column_dimensions["B"].width = 15
        ws2.column_dimensions["C"].width = 45
        from collections import Counter
        all_x = [x.strip() for e in entries for x in (e.get("variabel_x") or "").split(",")
                 if x.strip() and x.strip() != "-"]
        for i, (x_var, count) in enumerate(Counter(all_x).most_common(), 1):
            row = i + 2
            fill = alt_fill if i % 2 == 0 else wht_fill
            for col, val in enumerate([x_var, count, "→ Peluang / variabel tambahan"], 1):
                cell = ws2.cell(row=row, column=col, value=val)
                cell.font = body_font; cell.fill = fill
                cell.border = border; cell.alignment = left_wrap
        ws2.freeze_panes = "A3"
    wb.save(str(output_path))

def run_extract(outdir: Path, ai_key: str | None):
    global OPENROUTER_KEY
    if ai_key:
        OPENROUTER_KEY = ai_key
    pdfs = sorted(outdir.glob("*.pdf"))
    if not pdfs:
        err(f"Tidak ada PDF di {outdir} — tidak ada yang bisa diekstrak.")
        return
    ai_mode = bool(OPENROUTER_KEY)
    if ai_mode:
        info(f"Mode AI aktif — mengekstrak {len(pdfs)} PDF...")
    else:
        warn("Tanpa OpenRouter key → Excel berisi metadata (judul/penulis/tahun/jurnal).")
        warn("Isi key untuk analisis AI (X/Y/metode/hasil).")
    entries = []
    csv_rows = {}
    csv_path = outdir / "hasil_pencarian.csv"
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                csv_rows[r.get("Title", "")[:50]] = r
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name[:60]}...")
        if ai_mode:
            text = extract_pdf_text(pdf)
            entry = parse_with_ai(text, pdf.name) if text else fallback_entry(pdf.name)
            time.sleep(1)
        else:
            meta = csv_rows.get(pdf.name[7:57] if pdf.name.startswith("[") else pdf.name[:50], {})
            entry = fallback_entry(pdf.name)
            entry.update({"judul": pdf.name,
                          "penulis": meta.get("Authors", "-") or "-",
                          "tahun": str(meta.get("Year", "-") or "-"),
                          "jurnal": meta.get("Journal", "-") or "-"})
        entries.append(entry)
        ok("ok")
    out_xlsx = outdir / "tabel_perbandingan.xlsx"
    build_excel(entries, out_xlsx, ai_mode)
    ok(f"Excel tersimpan: {out_xlsx}")

# ═══════════════════════════════════════════════════════════════════════════
# Orkestrasi: mode dipandu + CLI
# ═══════════════════════════════════════════════════════════════════════════
def tanya(pesan: str, default=None) -> str:
    if default is not None:
        jwb = input(f"{pesan} [{default}]: ").strip()
        return jwb if jwb else str(default)
    while True:
        jwb = input(f"{pesan}: ").strip()
        if jwb:
            return jwb
        print("  ⚠ Tidak boleh kosong, coba lagi.")

def interactive():
    bold("\n╔══════════════════════════════════════════╗")
    bold("║   📚 Jurnal Finder — Skripsi             ║")
    bold("║   Cari → Download → Analisis             ║")
    bold("╚══════════════════════════════════════════╝\n")
    print("Ceritakan jurnal seperti apa yang kamu mau. Boleh Bahasa Indonesia.\n")

    print("1️⃣  Topik / judul penelitian kamu?")
    print("   Contoh: 'pengaruh inflasi terhadap harga saham'")
    topik = tanya("   Topik")
    print("\n2️⃣  Variabel X (bebas/independen)? Kosongkan kalau tidak ada.")
    print("   Contoh: 'inflasi, suku bunga' / 'ESG disclosure'")
    var_x = input("   Variabel X (Enter untuk skip): ").strip()
    print("\n3️⃣  Variabel Y (terikat/dependen)? Kosongkan kalau tidak ada.")
    print("   Contoh: 'harga saham' / 'nilai perusahaan'")
    var_y = input("   Variabel Y (Enter untuk skip): ").strip()

    print("\n🌐 Menerjemahkan ke Inggris (gratis)...")
    topik_en, m1 = translate_id_en(topik)
    x_en, m2 = translate_id_en(var_x) if var_x else ("", "asli")
    y_en, m3 = translate_id_en(var_y) if var_y else ("", "asli")
    info(f"Topik: '{topik}' → '{topik_en}' ({m1})")
    if var_x:
        info(f"X: '{var_x}' → '{x_en}' ({m2})")
    if var_y:
        info(f"Y: '{var_y}' → '{y_en}' ({m3})")
    queries = [q for q in [topik_en, f"{x_en} {y_en}".strip()] if q]
    queries = list(dict.fromkeys(queries))  # dedup, jaga urutan
    print(f"\n4️⃣  Keyword pencarian: {', '.join(queries)}")
    ubah = input("   Ubah? (Enter = lanjut, atau ketik keyword Inggris pisah koma): ").strip()
    if ubah:
        queries = [k.strip() for k in ubah.split(",") if k.strip()] or queries

    print("\n5️⃣  Filter tahun? Rekomendasi 5-10 tahun terakhir.")
    pakai = input("   Filter tahun? (y/n) [y]: ").strip().lower()
    ys, ye = None, None
    if pakai != "n":
        ys, ye = int(tanya("   Dari tahun", default=2018)), int(tanya("   Sampai tahun", default=2024))
    limit = int(tanya("\n6️⃣  Cari berapa jurnal per keyword", default=10))
    email = tanya("\n7️⃣  Email kamu (untuk akses PDF gratis)", default="user@email.com")

    print("\n8️⃣  Login akun kampus (SSO) untuk download PDF paywall?")
    print("   Kalau dilewati, hanya PDF gratis yang terdownload.")
    session = None
    if load_session() and input("   Sesi lama ditemukan, pakai lagi? (y/n) [y]: ").strip().lower() != "n":
        session = load_session()
        ok("Memakai sesi tersimpan.")
    elif input("   Login sekarang? (y/n) [y]: ").strip().lower() != "n":
        cmd_login()
        session = load_session()

    print("\n" + "─" * 45)
    bold("  Ringkasan:")
    print(f"  🔍 Keyword : {', '.join(queries)}")
    if ys:
        print(f"  📅 Tahun   : {ys} – {ye}")
    print(f"  📄 Jumlah  : {limit} per keyword")
    print(f"  🔑 Sesi SSO: {'ya' if session else 'tidak (gratis saja)'}")
    print("─" * 45)
    if input("\nMulai cari + download? (y/n) [y]: ").strip().lower() == "n":
        print("Oke, dibatalin.")
        return
    print()
    outdir = run_search_download(queries, limit, ys, ye, email, session, DOWNLOAD_DIR)

    print("\n9️⃣  Ekstrak semua jurnal jadi tabel Excel analisis?")
    print("   - Dengan OpenRouter key (gratis): kolom X/Y/metode/hasil/teori terisi AI")
    print("   - Tanpa key: Excel metadata saja (judul/penulis/tahun/jurnal)")
    if input("   Ekstrak sekarang? (y/n) [y]: ").strip().lower() != "n":
        ai_key = input("   OpenRouter key (Enter = tanpa AI): ").strip() or None
        run_extract(outdir, ai_key)
    bold("\n🎉 Beres! Cek folder ./jurnal_download/\n")

def main():
    parser = argparse.ArgumentParser(
        description="📚 Jurnal Finder — cari + download + analisis (boleh Bahasa Indonesia)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Contoh:
  python jurnal_finder.py
  python jurnal_finder.py --topik "pengaruh inflasi terhadap harga saham" -n 10
  python jurnal_finder.py --keyword-en "inflation stock prices" --skip-login --no-extract
        """)
    parser.add_argument("--topik", default=None, help="Topik (boleh Indonesia, auto-translate)")
    parser.add_argument("--x", default="", help="Variabel X")
    parser.add_argument("--y", default="", help="Variabel Y")
    parser.add_argument("--keyword-en", nargs="+", default=None, help="Keyword Inggris langsung (lewati translate)")
    parser.add_argument("-n", "--limit", type=int, default=10)
    parser.add_argument("--tahun", nargs=2, type=int, metavar=("DARI", "SAMPAI"), default=None)
    parser.add_argument("-e", "--email", default="user@email.com")
    parser.add_argument("--skip-login", action="store_true", help="Tanpa sesi SSO (hanya PDF gratis)")
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--ai-key", default=None, help="OpenRouter key untuk ekstrak AI")
    args = parser.parse_args()

    if not args.topik and not args.keyword_en:
        interactive()
        return
    queries = args.keyword_en or []
    if args.topik and not args.keyword_en:
        te, _ = translate_id_en(args.topik)
        xe, _ = translate_id_en(args.x) if args.x else ("", "")
        ye, _ = translate_id_en(args.y) if args.y else ("", "")
        queries = list(dict.fromkeys(q for q in [te, f"{xe} {ye}".strip()] if q))
    ys, ye = (args.tahun[0], args.tahun[1]) if args.tahun else (None, None)
    session = None if args.skip_login else load_session()
    outdir = run_search_download(queries, args.limit, ys, ye, args.email, session, DOWNLOAD_DIR)
    if not args.no_extract:
        run_extract(outdir, args.ai_key)

if __name__ == "__main__":
    main()
