#!/usr/bin/env python3
"""
jurnal_finder.py - Cari & download jurnal ilmiah GRATIS (tanpa auth).

Alur (dipandu, boleh Bahasa Indonesia):
  1. Ceritakan topik / judul / variabel  → otomatis diterjemahkan ke Inggris (gratis)
  2. Tool mencari (OpenAlex + DOAJ + arXiv + CrossRef, gratis tanpa key)
  3. Download semua PDF yang bisa diakses gratis
  4. Pilihan: ekstrak semua PDF jadi tabel Excel analisis perbandingan

Sumber pencarian (semua gratis, tanpa API key):
  - OpenAlex: ~250M paper, metadata lengkap + OA links
  - DOAJ: jurnal open access, PDF langsung via OJS
  - arXiv: preprint Komputer, AI, Matematika, Fisika
  - CrossRef: metadata dari Scopus/ScienceDirect, DOI + cross-ref

Download: hanya dari sumber yang menyediakan PDF gratis.
Tidak perlu login, API key, atau email.

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
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
DOAJ_API       = "https://doaj.org/api/search/articles"
ARXIV_API      = "https://export.arxiv.org/api/query"
CROSSREF_API   = "https://api.crossref.org/works"

DOWNLOAD_DIR = Path.home() / "jurnal_download"

OPENROUTER_MODEL = "google/gemma-4-31b-it:free"
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
                    year_start: int = None, year_end: int = None) -> list:
    info(f"Mencari: '{query}' ...")
    params = {"search": query, "per-page": min(limit, 200),
              "sort": "cited_by_count:desc", "select": ",".join([
                  "id", "doi", "title", "publication_year", "authorships",
                  "cited_by_count", "open_access", "primary_location",
                  "best_oa_location"])}
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
# TAHAP 2b — Cari jurnal via DOAJ (Directory of Open Access Journals)
# DOAJ hanya index journal open access → semua fulltext tersedia gratis.
# ═══════════════════════════════════════════════════════════════════════════
def search_doaj(query: str, limit: int = 10) -> list:
    """Cari artikel di DOAJ. Return list dict dengan format serupa OpenAlex."""
    info(f"Mencari di DOAJ: '{query}' ...")
    try:
        resp = requests.get(
            f"{DOAJ_API}/{requests.utils.quote(query)}",
            params={"page": 1, "pageSize": min(limit, 100)},
            headers={**HEADERS, "Accept": "application/json"},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        err(f"DOAJ gagal: {e}")
        return []

    if resp.status_code != 200:
        err(f"DOAJ HTTP {resp.status_code}")
        return []

    data = resp.json()
    results = []
    for item in data.get("results", []):
        bib = item.get("bibjson", {})
        doi = next(
            (i.get("id") for i in bib.get("identifier", []) if i.get("type") == "doi"),
            None,
        )
        # Ambil fulltext URL
        fulltext_url = None
        for link in bib.get("link", []):
            if link.get("content_type") == "PDF":
                fulltext_url = link.get("url")
                break
        if not fulltext_url:
            for link in bib.get("link", []):
                if link.get("type") == "fulltext":
                    fulltext_url = link.get("url")
                    break

        # Ekstrak direct PDF download URL dari halaman OJS
        pdf_url = _extract_ojs_pdf(fulltext_url) if fulltext_url else None

        authors = [{"name": a.get("name", "?")} for a in bib.get("author", [])[:3]]
        results.append({
            "paperId": f"doi:{doi.lower()}" if doi else f"doaj:{item.get('id', '')}",
            "title": bib.get("title") or "Untitled",
            "authors": authors,
            "year": int(bib.get("year") or 0) or None,
            "externalIds": {"DOI": doi} if doi else {},
            "citationCount": 0,
            "openAccessPdf": {"url": pdf_url or fulltext_url} if (pdf_url or fulltext_url) else None,
            "journal": bib.get("journal", {}).get("title") or "-",
            "_source": "doaj",
        })
    ok(f"DOAJ: {len(results)} artikel ditemukan")
    return results


def _extract_ojs_pdf(article_url: str) -> str | None:
    """Ekstrak direct PDF download URL dari halaman OJS (Open Journal Systems)."""
    if not article_url:
        return None
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.status_code != 200:
            return None
        html = resp.text
        import re
        # Pattern 1: /article/download/{article_id}/{galley_id}/{...}
        m = re.search(r'href="([^"]*article/download/\d+/\d+[^"]*)"', html)
        if m:
            url = m.group(1)
            if not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(article_url, url)
            return url
        # Pattern 2: /article/view/{article_id}/{galley_id}
        m = re.search(r'/article/view/(\d+)/(\d+)', html)
        if m:
            aid, gid = m.group(1), m.group(2)
            base = article_url.split("/article/")[0]
            return f"{base}/article/download/{aid}/{gid}"
        # Pattern 3: href langsung ke PDF
        m = re.search(r'href="([^"]*\.pdf[^"]*)"', html, re.I)
        if m:
            url = m.group(1)
            if not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(article_url, url)
            return url
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 2c — Cari jurnal via arXiv (preprint: Komputer, AI, Matematika, Fisika)
# arXiv menyediakan PDF langsung tanpa paywall.
# ═══════════════════════════════════════════════════════════════════════════
def search_arxiv(query: str, limit: int = 10) -> list:
    """Cari artikel di arXiv. Return list dict dengan format serupa OpenAlex."""
    import re
    info(f"Mencari di arXiv: '{query}' ...")
    try:
        resp = requests.get(
            ARXIV_API,
            params={"search_query": f"all:{query}", "max_results": min(limit, 50)},
            headers=HEADERS,
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        err(f"arXiv gagal: {e}")
        return []

    if resp.status_code != 200:
        err(f"arXiv HTTP {resp.status_code}")
        return []

    xml = resp.text
    entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
    results = []
    for entry in entries:
        title = re.findall(r"<title>(.*?)</title>", entry, re.S)
        title = " ".join((title[0] or "").split()) if title else "Untitled"

        # Authors
        authors_raw = re.findall(r"<author>\s*<name>(.*?)</name>", entry, re.S)
        authors = [{"name": a.strip()} for a in authors_raw[:3]]

        # PDF link
        pdf_url = None
        for link in re.findall(r'<link[^>]+href="([^"]+)"', entry):
            if "pdf" in link.lower():
                pdf_url = link
                break

        # DOI (opsional, tidak semua arXiv paper punya DOI)
        doi = None
        doi_match = re.findall(r"<doi>(.*?)</doi>", entry, re.S)
        if doi_match and doi_match[0].strip():
            doi = doi_match[0].strip()

        # Published year
        pub = re.findall(r"<published>(.*?)</published>", entry, re.S)
        year = int(pub[0][:4]) if pub and pub[0][:4].isdigit() else None

        # arXiv ID
        arxiv_id = re.findall(r"<id>(.*?)</id>", entry, re.S)
        arxiv_id = arxiv_id[0].strip() if arxiv_id else ""

        results.append({
            "paperId": f"arxiv:{arxiv_id}" if arxiv_id else f"doi:{doi.lower()}" if doi else "",
            "title": title,
            "authors": authors,
            "year": year,
            "externalIds": {"DOI": doi, "arXiv": arxiv_id} if doi else {"arXiv": arxiv_id},
            "citationCount": 0,
            "openAccessPdf": {"url": pdf_url} if pdf_url else None,
            "journal": "arXiv",
            "_source": "arxiv",
        })
    ok(f"arXiv: {len(results)} artikel ditemukan")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 2d — Cari jurnal via CrossRef (metadata dari Scopus/ScienceDirect)
# CrossRef menyediakan metadata lengkap dari ~150M paper. Gratis tanpa key.
# Tidak ada PDF langsung, tapi DOI-nya bisa dipakai untuk cross-reference.
# ═══════════════════════════════════════════════════════════════════════════
def search_crossref(query: str, limit: int = 10) -> list:
    """Cari artikel di CrossRef. Return list dict dengan format serupa OpenAlex."""
    info(f"Mencari di CrossRef: '{query}' ...")
    try:
        resp = requests.get(
            CROSSREF_API,
            params={
                "query": query,
                "rows": min(limit, 50),
                "select": "DOI,title,author,abstract,link,published-print,published-online",
            },
            headers={**HEADERS, "Accept": "application/json"},
            timeout=20,
        )
    except requests.exceptions.RequestException as e:
        err(f"CrossRef gagal: {e}")
        return []

    if resp.status_code != 200:
        err(f"CrossRef HTTP {resp.status_code}")
        return []

    data = resp.json()
    results = []
    for item in data.get("message", {}).get("items", []):
        doi = item.get("DOI")
        title_list = item.get("title", [])
        title = title_list[0] if title_list else "Untitled"

        # Authors
        authors_raw = item.get("author", [])
        authors = [{"name": f"{a.get('given', '')} {a.get('family', '')}".strip()} for a in authors_raw[:3]]

        # Year
        year = None
        for date_field in ["published-print", "published-online"]:
            parts = item.get(date_field, {}).get("date-parts", [[]])
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break

        # PDF link (jika ada)
        pdf_url = None
        for link in item.get("link", []):
            if "pdf" in link.get("content-type", ""):
                pdf_url = link.get("URL")
                break

        results.append({
            "paperId": f"doi:{doi.lower()}" if doi else "",
            "title": title,
            "authors": authors,
            "year": year,
            "externalIds": {"DOI": doi} if doi else {},
            "citationCount": 0,
            "openAccessPdf": {"url": pdf_url} if pdf_url else None,
            "journal": "-",
            "_source": "crossref",
        })
    ok(f"CrossRef: {len(results)} artikel ditemukan")
    return results


# ═══════════════════════════════════════════════════════════════════════════
# TAHAP 3 — Download PDF (gratis saja, tanpa auth)
# ═══════════════════════════════════════════════════════════════════════════
def download_pdf(url: str, filepath: Path) -> str:
    """Download PDF tanpa auth. Return 'ok' | 'fail'."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
    except requests.exceptions.RequestException:
        return "fail"
    if resp.status_code in (401, 403):
        return "fail"
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

def safe_filename(title: str, year=None, max_len: int = 80) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")
    name = "".join(c if c in keep else "_" for c in (title or ""))
    name = name[:max_len].strip() or "untitled"
    return (f"[{year}] {name}" if year else name) + ".pdf"

def run_search_download(queries: list[str], limit: int, year_start: int, year_end: int,
                        outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    all_papers, seen = [], set()
    for kw in queries:
        for p in search_openalex(kw, limit=limit, year_start=year_start,
                                 year_end=year_end):
            key = (p.get("externalIds") or {}).get("DOI", "") or p.get("paperId")
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)
        for p in search_doaj(kw, limit=limit):
            key = (p.get("externalIds") or {}).get("DOI", "") or p.get("paperId")
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)
        for p in search_arxiv(kw, limit=limit):
            key = (p.get("externalIds") or {}).get("arXiv", "") or p.get("paperId")
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)
        for p in search_crossref(kw, limit=limit):
            key = (p.get("externalIds") or {}).get("DOI", "") or p.get("paperId")
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)
        time.sleep(1)
    bold(f"\nTotal unik: {len(all_papers)} paper\n")
    results, manual, ndone = [], [], 0
    for i, paper in enumerate(all_papers, 1):
        title   = paper.get("title", "Untitled")
        year    = paper.get("year")
        authors = ", ".join(a["name"] for a in paper.get("authors", [])[:3])
        doi     = (paper.get("externalIds") or {}).get("DOI")
        print(f"[{i}/{len(all_papers)}] {title[:70]}...")
        status, source = "❌ Manual", "-"
        pdf_url = (paper.get("openAccessPdf") or {}).get("url")
        if pdf_url:
            src = paper.get("_source", "")
            source = {"doaj": "DOAJ", "arxiv": "arXiv"}.get(src, "Open Access")

        # ── Coba download dari URL yang sudah ada ──
        if pdf_url:
            if download_pdf(pdf_url, outdir / safe_filename(title, year)) == "ok":
                ok("Downloaded (gratis)"); status, ndone = "✅ Downloaded", ndone + 1
            else:
                time.sleep(3)
                if download_pdf(pdf_url, outdir / safe_filename(title, year)) == "ok":
                    ok("Downloaded (gratis)"); status, ndone = "✅ Downloaded", ndone + 1

        # ── Cross-reference: cari judul di DOAJ ──
        if status != "✅ Downloaded" and title and title != "Untitled":
            doaj_hits = search_doaj(title[:80], limit=1)
            for hit in doaj_hits:
                hit_url = (hit.get("openAccessPdf") or {}).get("url")
                if hit_url and download_pdf(hit_url, outdir / safe_filename(title, year)) == "ok":
                    ok("Downloaded (DOAJ cross-ref)"); status, source, ndone = "✅ Downloaded", "DOAJ", ndone + 1
                    break

        # ── Cross-reference: cari judul di arXiv ──
        if status != "✅ Downloaded" and title and title != "Untitled":
            arxiv_hits = search_arxiv(title[:80], limit=1)
            for hit in arxiv_hits:
                hit_url = (hit.get("openAccessPdf") or {}).get("url")
                if hit_url and download_pdf(hit_url, outdir / safe_filename(title, year)) == "ok":
                    ok("Downloaded (arXiv cross-ref)"); status, source, ndone = "✅ Downloaded", "arXiv", ndone + 1
                    break

        # ── Cross-reference: cari DOI di CrossRef untuk PDF link ──
        if status != "✅ Downloaded" and doi:
            xref_hits = search_crossref(f"doi:{doi}", limit=1)
            for hit in xref_hits:
                hit_url = (hit.get("openAccessPdf") or {}).get("url")
                if hit_url and download_pdf(hit_url, outdir / safe_filename(title, year)) == "ok":
                    ok("Downloaded (CrossRef cross-ref)"); status, source, ndone = "✅ Downloaded", "CrossRef", ndone + 1
                    break

        if status != "✅ Downloaded":
            manual.append({"title": title, "doi": doi or "-",
                           "year": year, "link": f"https://doi.org/{doi}" if doi else "-"})
        results.append({"No": i, "Title": title, "Authors": authors, "Year": year,
                        "DOI": doi or "-", "Citations": paper.get("citationCount", 0),
                        "Status": status, "Source": source if "Downloaded" in status else "-"})
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

def parse_offline(text: str, filename: str, csv_meta: dict = None) -> dict:
    """Ekstrak metadata dari PDF text + filename + CSV data (100% offline)."""
    import re
    entry = fallback_entry(filename)

    # ── Filename: [Year] Title.pdf → extract year + title ──
    m = re.match(r"\[(\d{4})\]\s*(.+?)\.pdf", filename)
    if m:
        entry["tahun"] = m.group(1)
        raw_title = m.group(2).strip()
        # Bersihkan underscore jadi spasi
        raw_title = re.sub(r"[_]+", " ", raw_title).strip()
        entry["judul"] = raw_title

    # ── Prioritas: pakai CSV data (lebih akurat dari filename) ──
    if csv_meta:
        if csv_meta.get("Title") and len(csv_meta["Title"]) > len(entry["judul"]):
            entry["judul"] = csv_meta["Title"][:120]
        if csv_meta.get("Authors"):
            entry["penulis"] = csv_meta["Authors"][:80]
        if csv_meta.get("Year"):
            entry["tahun"] = str(csv_meta["Year"])

    # ── Ekstrak dari PDF text ──
    if not text:
        return entry

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    text_lower = text.lower()

    # ── Penulis: dari CSV atau cari di text ──
    if entry["penulis"] == "-":
        for i, line in enumerate(lines[:20]):
            if re.match(r"^(abstract|abstrak|background|keywords)[:\s]*$", line.lower()):
                # Penulis ada di baris sebelum abstract
                for j in range(max(0, i-5), i):
                    candidate = lines[j]
                    # Ciri nama: ada huruf kapital berurutan + afiliasi
                    if (re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", candidate) and
                        len(candidate) > 10 and len(candidate) < 200 and
                        not any(kw in candidate.lower() for kw in ["abstract", "keywords", "copyright"])):
                        entry["penulis"] = candidate[:80]
                        break
                break

    # ── Jurnal: dari filename (sudah bersih) ──
    if entry["jurnal"] == "-":
        # Filename pattern: [Year] Journal Name.pdf
        m2 = re.match(r"\[\d{4}\]\s*(.+?)\.pdf", filename)
        if m2:
            journal = m2.group(1).strip()
            journal = re.sub(r"[_]+", " ", journal).strip()
            # Jika judul sama dengan jurnal, itu bukan jurnal
            if journal != entry["judul"]:
                entry["jurnal"] = journal

    # ── Abstract ──
    for i, line in enumerate(lines):
        if re.match(r"^(abstract|abstrak)[:\s]*$", line.lower()):
            abstract_lines = []
            for j in range(i+1, min(i+15, len(lines))):
                if re.match(r"^(keywords|istilah|introduction|pendahuluan|1[\.\s])", lines[j].lower()):
                    break
                abstract_lines.append(lines[j])
            if abstract_lines:
                entry["abstract"] = " ".join(abstract_lines)[:500]
            break

    # ── Metode ──
    metode_patterns = [
        (r"\bpanel data\b", "Panel Data"),
        (r"\bfixed.?effect\b", "Fixed Effect"),
        (r"\brandom.?effect\b", "Random Effect"),
        (r"\bgmm\b", "GMM"),
        (r"\blogistic regression\b", "Logistic Regression"),
        (r"\blinear regression\b", "Linear Regression"),
        (r"\bregression\b", "Regression"),
        (r"\banova\b", "ANOVA"),
        (r"\bmeta.?analysis\b", "Meta-Analysis"),
        (r"\bsystematic review\b", "Systematic Review"),
        (r"\bliterature review\b", "Literature Review"),
        (r"\bsurvey\b", "Survey"),
        (r"\bquestionnaire\b", "Questionnaire"),
        (r"\bexperiment\b", "Experiment"),
        (r"\bsimulation\b", "Simulation"),
        (r"\bqualitative\b", "Qualitative"),
        (r"\bquantitative\b", "Quantitative"),
        (r"\bmixed.?method\b", "Mixed Method"),
        (r"\bmachine learning\b", "Machine Learning"),
        (r"\bdeep learning\b", "Deep Learning"),
        (r"\bneural network\b", "Neural Network"),
        (r"\brandom forest\b", "Random Forest"),
        (r"\bdescriptive\b", "Descriptive"),
        (r"\bcorrelation\b", "Correlation"),
        (r"\bsem\b", "SEM"),
    ]
    metode_found = []
    for pattern, name in metode_patterns:
        if re.search(pattern, text_lower):
            metode_found.append(name)
    if metode_found:
        entry["metode"] = ", ".join(metode_found[:3])

    # ── Sampel ──
    sample_patterns = [
        r"(?:n|N)\s*=\s*([\d,.]+)",
        r"(\d[\d,.]*)\s*(?:participants|subjects|respondents|samples|patients|firms|companies)",
        r"sample\s*(?:of|size)\s*[:=]?\s*(\d[\d,.]*)",
    ]
    for pat in sample_patterns:
        m = re.search(pat, text, re.I)
        if m:
            entry["sampel"] = m.group(1).strip()
            break

    # ── Teori ──
    teori_list = [
        ("stakeholder theory", "Stakeholder Theory"),
        ("agency theory", "Agency Theory"),
        ("signaling theory", "Signaling Theory"),
        ("resource-based view", "RBV"),
        ("modern portfolio", "MPT"),
        ("efficient market", "EMH"),
        ("behavioral finance", "Behavioral Finance"),
        ("capital asset pricing", "CAPM"),
        ("fama-french", "Fama-French"),
        ("pecking order", "Pecking Order"),
        ("technology acceptance", "TAM"),
        ("planned behavior", "TPB"),
    ]
    teori_found = []
    for kw, name in teori_list:
        if kw in text_lower:
            teori_found.append(name)
    if teori_found:
        entry["teori"] = ", ".join(teori_found[:3])

    return entry

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
    pdfs = sorted(outdir.glob("*.pdf"))
    if not pdfs:
        err(f"Tidak ada PDF di {outdir} — tidak ada yang bisa diekstrak.")
        return

    # Load progress untuk resume
    progress_file = outdir / "_extract_progress.json"
    done_entries = {}
    if progress_file.exists():
        try:
            done_entries = json.loads(progress_file.read_text(encoding="utf-8"))
            info(f"Resume: {len(done_entries)} PDF sudah diekstrak sebelumnya")
        except Exception:
            done_entries = {}

    info(f"Mengekstrak {len(pdfs)} PDF (offline, tanpa API key)...")
    entries = []
    csv_rows = {}
    csv_path = outdir / "hasil_pencarian.csv"
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                csv_rows[r.get("Title", "")[:50]] = r
    for i, pdf in enumerate(pdfs, 1):
        pdf_key = pdf.name
        # Skip jika sudah diekstrak
        if pdf_key in done_entries:
            entries.append(done_entries[pdf_key])
            continue
        print(f"[{i}/{len(pdfs)}] {pdf.name[:60]}...")
        text = extract_pdf_text(pdf)
        # Cari metadata dari CSV — coba beberapa variasi key
        meta = {}
        for key_fn in [
            lambda: pdf.name[7:57] if pdf.name.startswith("[") else pdf.name[:50],
            lambda: pdf.name[:50],
            lambda: pdf.name.replace(".pdf", "")[:50],
        ]:
            try:
                k = key_fn()
                if k in csv_rows:
                    meta = csv_rows[k]
                    break
            except Exception:
                continue
        entry = parse_offline(text, pdf.name, meta)
        entries.append(entry)
        done_entries[pdf_key] = entry
        # Simpan progress setiap 5 file
        if i % 5 == 0:
            progress_file.write_text(json.dumps(done_entries, ensure_ascii=False, indent=2), encoding="utf-8")
        ok("ok")

    # Simpan progress final
    progress_file.write_text(json.dumps(done_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    out_xlsx = outdir / "tabel_perbandingan.xlsx"
    build_excel(entries, out_xlsx, False)
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

def menu_cari():
    """Menu: Cari & Download Jurnal."""
    bold("\n┌─────────────────────────────────────┐")
    bold("│  🔍 Cari & Download Jurnal          │")
    bold("└─────────────────────────────────────┘\n")

    print("Ceritakan jurnal seperti apa yang kamu mau.")
    print("Boleh Bahasa Indonesia — otomatis diterjemahkan.\n")

    topik = tanya("Topik / judul penelitian")
    var_x = input("Variabel X (Enter untuk skip): ").strip()
    var_y = input("Variabel Y (Enter untuk skip): ").strip()

    print("\n🌐 Menerjemahkan ke Inggris...")
    topik_en, m1 = translate_id_en(topik)
    x_en, m2 = translate_id_en(var_x) if var_x else ("", "asli")
    y_en, m3 = translate_id_en(var_y) if var_y else ("", "asli")
    info(f"Topik: '{topik}' → '{topik_en}' ({m1})")
    if var_x:
        info(f"X: '{var_x}' → '{x_en}' ({m2})")
    if var_y:
        info(f"Y: '{var_y}' → '{y_en}' ({m3})")

    queries = [q for q in [topik_en, f"{x_en} {y_en}".strip()] if q]
    queries = list(dict.fromkeys(queries))
    print(f"\nKeyword pencarian: {', '.join(queries)}")
    ubah = input("Ubah? (Enter = lanjut, atau ketik keyword pisah koma): ").strip()
    if ubah:
        queries = [k.strip() for k in ubah.split(",") if k.strip()] or queries

    print("\nFilter tahun?")
    pakai = input("   Filter tahun? (y/n) [y]: ").strip().lower()
    ys, ye = None, None
    if pakai != "n":
        ys = int(tanya("   Dari tahun", default=2018))
        ye = int(tanya("   Sampai tahun", default=2024))
    limit = int(tanya("Jurnal per keyword", default=10))

    print("\n" + "─" * 45)
    bold("  Ringkasan:")
    print(f"  🔍 Keyword : {', '.join(queries)}")
    if ys:
        print(f"  📅 Tahun   : {ys} – {ye}")
    print(f"  📄 Jumlah  : {limit} per keyword")
    print("─" * 45)
    if input("\nMulai cari + download? (y/n) [y]: ").strip().lower() == "n":
        return

    print()
    outdir = run_search_download(queries, limit, ys, ye, DOWNLOAD_DIR)

    # Tawarkan ekstrak
    print("\nEkstrak ke Excel?")
    print("  - 100% offline, tanpa API key")
    print("  - Resume: PDF sudah diproses akan di-skip")
    if input("  Ekstrak sekarang? (y/n) [y]: ").strip().lower() != "n":
        run_extract(outdir, None)

    bold("\n✅ Selesai! Cek folder ~/jurnal_download/\n")

def menu_ekstrak():
    """Menu: Ekstrak PDF yang sudah ada."""
    bold("\n┌─────────────────────────────────────┐")
    bold("│  📊 Ekstrak PDF → Excel             │")
    bold("└─────────────────────────────────────┘\n")

    pdfs = sorted(DOWNLOAD_DIR.glob("*.pdf")) if DOWNLOAD_DIR.exists() else []
    if not pdfs:
        err(f"Tidak ada PDF di {DOWNLOAD_DIR}")
        print("  Jalankan 'Cari & Download' terlebih dahulu.")
        return

    print(f"Ditemukan {len(pdfs)} PDF di {DOWNLOAD_DIR}/\n")
    print("Mode: 100% offline, tanpa API key, tidak perlu internet.")
    print("Resume: PDF yang sudah diekstrak akan di-skip.\n")

    run_extract(DOWNLOAD_DIR, None)
    bold("\n✅ Selesai!\n")

def menu_folder():
    """Menu: Ganti folder output."""
    global DOWNLOAD_DIR, EXTRACT_DIR
    bold("\n┌─────────────────────────────────────┐")
    bold("│  📁 Folder Output                   │")
    bold("└─────────────────────────────────────┘\n")

    print(f"Folder saat ini: {DOWNLOAD_DIR.resolve()}")
    new_dir = input("Folder baru (Enter = tetap sama): ").strip()
    if new_dir:
        DOWNLOAD_DIR = Path(new_dir)
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        ok(f"Folder diubah ke: {DOWNLOAD_DIR.resolve()}")

def interactive():
    global DOWNLOAD_DIR
    while True:
        bold("\n╔══════════════════════════════════════════╗")
        bold("║   📚 Jurnal Finder                      ║")
        bold("║   Cari → Download → Analisis            ║")
        bold("╚══════════════════════════════════════════╝\n")

        if DOWNLOAD_DIR.exists():
            pdf_count = len(list(DOWNLOAD_DIR.glob("*.pdf")))
            if pdf_count > 0:
                print(f"  📂 Folder: {DOWNLOAD_DIR.resolve()}")
                print(f"  📄 PDF tersedia: {pdf_count}")
                print()

        print("  1  🔍  Cari & Download Jurnal")
        print("  2  📊  Ekstrak PDF → Excel")
        print("  3  📁  Ganti Folder Output")
        print("  4  ❌  Keluar")
        print()

        pilihan = input("Pilih [1-4]: ").strip()

        if pilihan == "1":
            menu_cari()
        elif pilihan == "2":
            menu_ekstrak()
        elif pilihan == "3":
            menu_folder()
        elif pilihan == "4":
            bold("\n👋 Sampai jumpa!\n")
            break
        else:
            warn("Pilihan tidak valid.")

def main():
    parser = argparse.ArgumentParser(
        description="📚 Jurnal Finder — cari + download + analisis (boleh Bahasa Indonesia)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Contoh:
  python jurnal_finder.py
  python jurnal_finder.py --topik "pengaruh inflasi terhadap harga saham" -n 10
  python jurnal_finder.py --keyword-en "inflation stock prices" --no-extract
  python jurnal_finder.py --extract-only --ai-key YOUR_KEY   # ekstrak ulang
        """)
    parser.add_argument("--topik", default=None, help="Topik (boleh Indonesia, auto-translate)")
    parser.add_argument("--x", default="", help="Variabel X")
    parser.add_argument("--y", default="", help="Variabel Y")
    parser.add_argument("--keyword-en", nargs="+", default=None, help="Keyword Inggris langsung (lewati translate)")
    parser.add_argument("-n", "--limit", type=int, default=10)
    parser.add_argument("--tahun", nargs=2, type=int, metavar=("DARI", "SAMPAI"), default=None)
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--extract-only", action="store_true", help="Hanya ekstrak PDF yang sudah ada (tidak download ulang)")
    args = parser.parse_args()

    # Mode extract-only: ekstrak PDF yang sudah ada
    if args.extract_only:
        outdir = DOWNLOAD_DIR
        if not outdir.exists() or not list(outdir.glob("*.pdf")):
            err(f"Tidak ada PDF di {outdir}")
            return
        run_extract(outdir, None)
        return

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
    outdir = run_search_download(queries, args.limit, ys, ye, DOWNLOAD_DIR)
    if not args.no_extract:
        run_extract(outdir, None)

if __name__ == "__main__":
    main()
