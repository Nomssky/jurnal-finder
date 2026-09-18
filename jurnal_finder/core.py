#!/usr/bin/env python3
"""
jurnal_finder.py - Cari & download jurnal ilmiah GRATIS (tanpa auth).

Alur (dipandu, boleh Bahasa Indonesia):
  1. Ceritakan topik / judul / variabel + pilih BIDANG + (opsional) PENERBIT
     → diterjemahkan ke Inggris
  2. Tool mencari (OpenAlex + DOAJ + CrossRef, gratis tanpa key)
     - OpenAlex & CrossRef difilter per bidang dan/atau penerbit
  3. Download semua PDF yang bisa diakses gratis, lalu VERIFIKASI isi PDF
     (judul di halaman awal harus cocok — mencegah file salah isi)
  4. Pilihan: ekstrak semua PDF jadi tabel Excel analisis perbandingan

Sumber pencarian (semua gratis, tanpa API key):
  - OpenAlex: ~250M paper, metadata lengkap + OA links + topik/bidang
  - DOAJ: jurnal open access, PDF langsung via OJS
  - CrossRef: metadata dari Scopus/ScienceDirect/Emerald/dll (DOI + penerbit)
  - Unpaywall: cari PDF gratis dari DOI
  - arXiv: preprint (hanya dipakai untuk bidang "umum")

Catatan sumber berlangganan (ScienceDirect, Scopus, Emerald, Wiley,
Taylor & Francis, JSTOR, IEEE, dll) tidak bisa di-scrape otomatis tanpa
akses kampus. Tool tetap mengambil DOI-nya, lalu mencoba PDF gratis via
OpenAlex/Unpaywall/DOAJ; yang paywalled masuk manual_download.csv
(lengkap dengan link DOI untuk dibuka via akses kampus/perpus).

Pakai:
  jf                                              # mode dipandu (disarankan)
  jf --bidang ekonomi --penerbit elsevier --topik "..."
  jf --help                                       # daftar opsi lengkap
"""

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────
OPENALEX_API   = "https://api.openalex.org/works"
MYMEMORY_API   = "https://api.mymemory.translated.net/get"
DOAJ_API       = "https://doaj.org/api/search/articles"
ARXIV_API      = "https://export.arxiv.org/api/query"
CROSSREF_API   = "https://api.crossref.org/works"
UNPAYWALL_API  = "https://api.unpaywall.org/v2"

DOWNLOAD_DIR = Path.home() / "jurnal_download"

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Email untuk Unpaywall (wajib per aturan mereka, dipakai untuk cari PDF gratis dari DOI).
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "jurnal-finder@example.com")

# Bidang OpenAlex -> filter topic. `fields` = nama field OpenAlex yang lolos.
# "Decision Sciences" & "Social Sciences" disertakan pada sebagian bidang karena
# banyak riset adopsi teknologi/perilaku organisasi terklasifikasi di sana.
FIELD_PRESETS = {
    "ekonomi":    {"label": "Ekonomi / Ekonomi Pembangunan",
                   "fields": ["Economics, Econometrics and Finance"]},
    "akuntansi":  {"label": "Akuntansi",
                   "fields": ["Business, Management and Accounting",
                              "Economics, Econometrics and Finance",
                              "Decision Sciences"]},
    "manajemen":  {"label": "Manajemen / Bisnis",
                   "fields": ["Business, Management and Accounting",
                              "Decision Sciences"]},
    "keuangan":   {"label": "Keuangan / Perbankan",
                   "fields": ["Economics, Econometrics and Finance",
                              "Business, Management and Accounting"]},
    "umum":       {"label": "Semua bidang (tanpa filter)",
                   "fields": []},
}

# Penerbit yang punya fulltext sendiri. `match` = potongan nama penerbit
# (dicek substring, tanpa beda huruf besar/kecil) di metadata CrossRef/OpenAlex.
# Nama dicocokkan dengan beberapa varian karena CrossRef & OpenAlex berbeda
# penamaan (mis. "Emerald Publishing Limited" vs "Emerald").
# CATATAN: ini hanya MENYARING hasil dari penerbit tersebut; PDF-nya tetap
# hanya bisa di-download otomatis kalau versi Open Access-nya tersedia.
PUBLISHER_PRESETS = {
    "elsevier":       {"label": "Elsevier / ScienceDirect",
                       "match": ["Elsevier"]},
    "emerald":        {"label": "Emerald Insight",
                       "match": ["Emerald"]},
    "wiley":          {"label": "Wiley Online Library",
                       "match": ["Wiley", "Blackwell"]},
    "taylor-francis": {"label": "Taylor & Francis",
                       "match": ["Taylor & Francis", "Informa"]},
    "springer":       {"label": "Springer / Nature",
                       "match": ["Springer", "Nature Portfolio"]},
    "oxford":         {"label": "Oxford Academic",
                       "match": ["Oxford University Press", "Oxford University"]},
    "cambridge":      {"label": "Cambridge Core",
                       "match": ["Cambridge University Press", "Cambridge University"]},
    "ieee":           {"label": "IEEE Xplore",
                       "match": ["IEEE", "Institute of Electrical and Electronics"]},
    "asce":           {"label": "ASCE",
                       "match": ["American Society of Civil Engineers", "ASCE"]},
    "igi":            {"label": "IGI Global",
                       "match": ["IGI Global"]},
    "jstor":          {"label": "JSTOR",
                       "match": ["JSTOR"]},
    "sage":           {"label": "SAGE",
                       "match": ["SAGE"]},
}

# Database INDEKS / platform berlangganan: tidak punya fulltext sendiri, jadi
# "filter penerbit" tidak berlaku. Ditampilkan hanya sebagai catatan edukasi.
PAYWALLED_INDEXES = [
    "Scopus", "Embase", "EBSCOhost", "ProQuest", "Westlaw",
    "ClinicalKey", "McGraw-Hill Access",
]

# Minimal kemiripan judul (0-1) antara paper yang dicari dengan hasil cross-ref.
TITLE_MATCH_MIN = 0.72

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
# UTIL — Normalisasi & pencocokan judul (untuk mencegah file salah isi)
# ═══════════════════════════════════════════════════════════════════════════
_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "to", "and", "for", "with", "using",
    "study", "research", "analysis", "effect", "effects", "toward", "towards",
    "dan", "yang", "pada", "untuk", "terhadap", "dengan", "studi", "analisis",
}

def normalize_title(title: str) -> str:
    """Lowercase, buang tanda baca, rapikan spasi."""
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())

def title_tokens(title: str) -> set:
    """Token bermakna (buang stopword pendek) untuk perbandingan."""
    return {w for w in normalize_title(title).split() if len(w) > 2 and w not in _STOPWORDS}

def title_similarity(a: str, b: str) -> float:
    """Kemiripan 0-1 berbasis Jaccard + bonus substring (judul singkat)."""
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    na, nb = normalize_title(a), normalize_title(b)
    # Bonus jika salah satu judul termuat di judul lain (judul dipotong dsb.)
    if na and nb and (na in nb or nb in na):
        jaccard = max(jaccard, 0.9)
    return jaccard

def titles_match(a: str, b: str, threshold: float = TITLE_MATCH_MIN) -> bool:
    return title_similarity(a, b) >= threshold

def field_matches(paper: dict, preset: dict) -> bool:
    """Cek apakah paper masuk bidang yang dipilih (via primary_topic OpenAlex).

    Paper yang TIDAK punya info topik (mis. hasil CrossRef/DOAJ yang hanya
    menyimpan DOI & penerbit) tidak bisa dinilai → dibiarkan lolos, supaya
    sumber tanpa metadata topik tidak ikut terbuang semua.
    """
    if not preset or not preset.get("fields"):
        return True
    topic = paper.get("_topic") or {}
    if not topic:
        # Tidak ada data topik → jangan buang (biar tidak salah singkirkan).
        return True
    field = (topic.get("field") or {}).get("display_name") or ""
    if field in preset.get("fields", []):
        return True
    # Refinement opsional: kecocokan nama topic juga diterima.
    tname = (topic.get("display_name") or "").lower()
    for want in preset.get("topics", []) or []:
        if want.lower() in tname:
            return True
    return False

def publisher_matches(paper: dict, preset: dict) -> bool:
    """Cek apakah paper diterbitkan oleh penerbit yang dipilih."""
    if not preset or not preset.get("match"):
        return True
    pub = (paper.get("_publisher") or "").lower()
    if not pub:
        return False
    return any(want.lower() in pub for want in preset["match"])

# Kata umum dalam judul akademik yang biasanya mengurangi relevansi pencarian.
_QUERY_NOISE = {
    "factor", "factors", "influencing", "influence", "effect", "effects",
    "impact", "impacts", "intention", "intent", "adopt", "adoption", "adopting",
    "role", "study", "analysis", "analysing", "analyzing", "review",
    "toward", "towards", "on", "of", "the", "in", "to", "and", "for", "with",
    "using", "usage", "use", "based", "among", "between", "from", "a", "an",
}

def query_variants(kw: str) -> list[str]:
    """Hasilkan query ringkas (buang kata generik) untuk memperluas pencarian.

    Contoh: 'Factors influencing the intention to adopt ChatGPT in accounting'
      → ['Factors influencing ...', 'ChatGPT accounting']
    """
    words = re.findall(r"[A-Za-z0-9]+", kw)
    core_words = [w for w in words if w.lower() not in _QUERY_NOISE]
    variants = [kw]
    if len(core_words) >= 2:
        short = " ".join(core_words[:6])
        if short.lower() != kw.lower():
            variants.append(short)
    return variants

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
    source = loc.get("source") or {}
    src = source.get("display_name") or "-"
    publisher = source.get("host_organization_name") or ""
    pid = f"doi:{doi.lower()}" if doi else w.get("id", "")
    topic = w.get("primary_topic") or {}
    return {
        "paperId": pid, "title": w.get("title") or "Untitled", "authors": authors,
        "year": w.get("publication_year"), "externalIds": {"DOI": doi} if doi else {},
        "citationCount": w.get("cited_by_count", 0) or 0,
        "openAccessPdf": {"url": pdf_url} if pdf_url else None,
        "journal": src,
        "_source": "openalex",
        "_publisher": publisher,
        "_topic": topic,
        "_topic_field": ((topic.get("field") or {}).get("display_name")) or "-",
        "_topic_name": topic.get("display_name") or "-",
    }

def search_openalex(query: str, limit: int = 20,
                    year_start: int = None, year_end: int = None,
                    field_preset: dict = None,
                    publisher_preset: dict = None) -> list:
    info(f"Mencari: '{query}' ...")
    # Ambil berlebih karena hasil akan disaring (bidang & penerbit).
    fetch = min(limit * 5, 200)
    params = {"search": query, "per-page": fetch,
              "sort": "cited_by_count:desc", "select": ",".join([
                  "id", "doi", "title", "publication_year", "authorships",
                  "cited_by_count", "open_access", "primary_location",
                  "best_oa_location", "primary_topic"])}
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
            # Filter bidang (mis. ekonomi) & penerbit. Ambil berlebih lalu saring.
            if field_preset and field_preset.get("fields"):
                papers = [p for p in papers if field_matches(p, field_preset)]
            if publisher_preset and publisher_preset.get("match"):
                papers = [p for p in papers if publisher_matches(p, publisher_preset)]
            papers = papers[:limit]
            label = []
            if field_preset and field_preset.get("fields"):
                label.append(f"bidang: {field_preset['label']}")
            if publisher_preset and publisher_preset.get("match"):
                label.append(f"penerbit: {publisher_preset['label']}")
            ok(f"Ditemukan {len(papers)} paper"
               + (f" ({'; '.join(label)})" if label else ""))
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
def search_crossref(query: str, limit: int = 10,
                    publisher_preset: dict = None) -> list:
    """Cari artikel di CrossRef. Return list dict dengan format serupa OpenAlex."""
    info(f"Mencari di CrossRef: '{query}' ...")
    # Ambil lebih banyak dari batas akhir, karena hasil masih disaring penerbit.
    fetch = min(max(limit * 10, 50), 100)
    try:
        resp = requests.get(
            CROSSREF_API,
            params={
                "query": query,
                "rows": fetch,
                "select": "DOI,title,author,abstract,link,publisher,container-title,"
                          "short-container-title,volume,issue,page,"
                          "published-print,published-online",
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

        # Journal & publisher
        cont = item.get("container-title") or item.get("short-container-title") or []
        journal = cont[0] if cont else "-"
        publisher = item.get("publisher") or ""

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
            "journal": journal,
            "_source": "crossref",
            "_publisher": publisher,
            "_volume": item.get("volume"),
            "_issue": item.get("issue"),
            "_page": item.get("page"),
        })
    if publisher_preset and publisher_preset.get("match"):
        results = [r for r in results if publisher_matches(r, publisher_preset)]
        results = results[:limit]
    ok(f"CrossRef: {len(results)} artikel ditemukan")
    return results


def crossref_pdf_by_doi(doi: str) -> str | None:
    """Ambil link PDF (bila ada) untuk satu DOI via endpoint CrossRef langsung."""
    try:
        resp = requests.get(f"{CROSSREF_API}/{doi}", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        links = resp.json().get("message", {}).get("link", [])
        for link in links:
            if "pdf" in (link.get("content-type") or ""):
                return link.get("URL")
    except requests.exceptions.RequestException:
        return None
    return None


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
        # Tolak halaman HTML (login/landing) walau status 200.
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "pdf" not in ctype and "octet-stream" not in ctype:
            # Beberapa server tidak set Content-Type benar → cek byte awal nanti.
            pass
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        with open(filepath, "rb") as f:
            head = f.read(4)
        if head != b"%PDF":
            filepath.unlink(missing_ok=True)
            return "fail"
        return "ok"
    except Exception:
        filepath.unlink(missing_ok=True)
        return "fail"

def unpaywall_pdf_url(doi: str) -> str | None:
    """Cari URL PDF gratis dari DOI via Unpaywall (butuh email yang valid)."""
    if not doi:
        return None
    try:
        resp = requests.get(
            f"{UNPAYWALL_API}/{requests.utils.quote(doi)}",
            params={"email": UNPAYWALL_EMAIL},
            headers=HEADERS, timeout=20,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("is_oa"):
            return None
        # Utamakan best_oa_location, lalu lokasi OA pertama.
        loc = data.get("best_oa_location") or {}
        url = loc.get("url_for_pdf") or loc.get("url")
        if url:
            return url
        for loc in data.get("oa_locations", []) or []:
            url = loc.get("url_for_pdf") or loc.get("url")
            if url:
                return url
    except Exception:
        return None
    return None

def pdf_title_matches(pdf_path: Path, expected_title: str) -> bool:
    """Validasi isi PDF: judul paper harus muncul di halaman awal.

    Return True jika (a) judul cocok di teks, atau (b) teks tak bisa
    diekstrak (jangan tolak hanya karena ekstraksi gagal).
    """
    if not expected_title or expected_title == "Untitled":
        return True
    text = extract_pdf_text(pdf_path, max_chars=1500)
    if not text:
        return True  # tak bisa diverifikasi -> jangan buang
    return title_similarity(text, expected_title) >= 0.55 or titles_match(
        text[:400], expected_title, threshold=0.5)

def safe_filename(title: str, year=None, max_len: int = 80) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")
    name = "".join(c if c in keep else "_" for c in (title or ""))
    name = name[:max_len].strip() or "untitled"
    return (f"[{year}] {name}" if year else name) + ".pdf"

def _download_and_verify(url: str, title: str, year, outdir: Path) -> bool:
    """Download PDF ke nama file judul, lalu verifikasi isi cocok. Hapus jika mismatch."""
    if not url:
        return False
    dest = outdir / safe_filename(title, year)
    if download_pdf(url, dest) != "ok":
        return False
    if not pdf_title_matches(dest, title):
        dest.unlink(missing_ok=True)
        warn(f"Isi PDF tidak cocok dengan judul → dibuang: {title[:60]}")
        return False
    return True


def run_search_download(queries: list[str], limit: int, year_start: int, year_end: int,
                        outdir: Path, field_preset: dict = None,
                        publisher_preset: dict = None):
    outdir.mkdir(parents=True, exist_ok=True)
    # arXiv = fisika/CS; hanya dipakai kalau tidak memfilter bidang ekonomi.
    use_arxiv = not (field_preset and field_preset.get("fields"))
    all_papers, seen = [], set()

    def _add(papers, key_field="DOI"):
        for p in papers:
            key = (p.get("externalIds") or {}).get(key_field, "") or p.get("paperId")
            if key and key not in seen:
                seen.add(key)
                all_papers.append(p)

    # Pakai query asli + varian ringkas agar hasil lebih luas (query panjang
    # yang auto-translate sering mendilusi relevansi).
    search_terms = []
    for q in queries:
        for v in query_variants(q):
            if v and v.lower() not in [t.lower() for t in search_terms]:
                search_terms.append(v)

    for kw in search_terms:
        _add(search_openalex(kw, limit=limit, year_start=year_start,
                             year_end=year_end, field_preset=field_preset,
                             publisher_preset=publisher_preset))
        _add(search_doaj(kw, limit=limit))
        if use_arxiv:
            _add(search_arxiv(kw, limit=limit), key_field="arXiv")
        _add(search_crossref(kw, limit=limit, publisher_preset=publisher_preset))
        time.sleep(1)
    # Saring penerbit untuk semua sumber (DOAJ/arXiv umumnya non-penerbit besar).
    if publisher_preset and publisher_preset.get("match"):
        all_papers = [p for p in all_papers if publisher_matches(p, publisher_preset)]
    bold(f"\nTotal unik: {len(all_papers)} paper\n")
    if not all_papers:
        warn("Tidak ada paper yang cocok dengan filter Anda.")
        tips = []
        if field_preset and field_preset.get("fields"):
            tips.append("coba bidang 'umum'")
        if publisher_preset and publisher_preset.get("match"):
            tips.append("hilangkan filter penerbit (pilih 'Semua penerbit')")
        tips.append("pakai kata kunci yang lebih umum")
        print("  💡 Tips: " + "; ".join(tips) + ".")
        return outdir
    results, manual, ndone, rejected = [], [], 0, 0
    for i, paper in enumerate(all_papers, 1):
        title   = paper.get("title", "Untitled")
        year    = paper.get("year")
        authors = ", ".join(a["name"] for a in paper.get("authors", [])[:3])
        doi     = (paper.get("externalIds") or {}).get("DOI")
        publisher = paper.get("_publisher") or "-"
        journal = paper.get("journal") or "-"
        print(f"[{i}/{len(all_papers)}] {title[:70]}...")
        status, source = "❌ Manual", "-"
        pdf_url = (paper.get("openAccessPdf") or {}).get("url")
        if pdf_url and paper.get("_source") in ("doaj", "arxiv"):
            source = {"doaj": "DOAJ", "arxiv": "arXiv"}.get(paper.get("_source"), "Open Access")

        # ── 1. Coba download dari URL yang sudah ada ──
        if pdf_url:
            if _download_and_verify(pdf_url, title, year, outdir):
                ok("Downloaded (gratis)"); status, source, ndone = "✅ Downloaded", source, ndone + 1

        # ── 2. Unpaywall: DOI → PDF gratis ──
        if status != "✅ Downloaded" and doi:
            upw = unpaywall_pdf_url(doi)
            if upw and _download_and_verify(upw, title, year, outdir):
                ok("Downloaded (Unpaywall)"); status, source, ndone = "✅ Downloaded", "Unpaywall", ndone + 1

        # ── 3. Cross-ref DOAJ — WAJIB judul cocok dulu (hindari file salah isi) ──
        if status != "✅ Downloaded" and title and title != "Untitled":
            for hit in search_doaj(title[:80], limit=3):
                if not titles_match(hit.get("title", ""), title):
                    continue
                hit_url = (hit.get("openAccessPdf") or {}).get("url")
                if _download_and_verify(hit_url, title, year, outdir):
                    ok("Downloaded (DOAJ cross-ref)"); status, source, ndone = "✅ Downloaded", "DOAJ", ndone + 1
                    break

        # ── 4. Cross-ref arXiv (judul harus cocok) ──
        if use_arxiv and status != "✅ Downloaded" and title and title != "Untitled":
            for hit in search_arxiv(title[:80], limit=3):
                if not titles_match(hit.get("title", ""), title):
                    continue
                hit_url = (hit.get("openAccessPdf") or {}).get("url")
                if _download_and_verify(hit_url, title, year, outdir):
                    ok("Downloaded (arXiv cross-ref)"); status, source, ndone = "✅ Downloaded", "arXiv", ndone + 1
                    break

        # ── 5. CrossRef: ambil link PDF langsung via endpoint DOI (bukan search) ──
        if status != "✅ Downloaded" and doi:
            hit_url = crossref_pdf_by_doi(doi)
            if hit_url and _download_and_verify(hit_url, title, year, outdir):
                ok("Downloaded (CrossRef)"); status, source, ndone = "✅ Downloaded", "CrossRef", ndone + 1

        if status != "✅ Downloaded":
            manual.append({"Title": title, "Year": year or "-", "Publisher": publisher,
                           "Journal": journal, "DOI": doi or "-",
                           "Link DOI": f"https://doi.org/{doi}" if doi else "-",
                           "Cara ambil": "Buka link di browser pakai akses kampus/perpus"})
        results.append({"No": i, "Title": title, "Authors": authors, "Year": year,
                        "DOI": doi or "-", "Citations": paper.get("citationCount", 0),
                        "Bidang": paper.get("_topic_field", "-"),
                        "Publisher": publisher,
                        "Journal": journal,
                        "Status": status,
                        "Source": source if "Downloaded" in status else "-"})
    if results:
        with open(outdir / "hasil_pencarian.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader(); w.writerows(results)
    if manual:
        with open(outdir / "manual_download.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Title", "Year", "Publisher", "Journal",
                                              "DOI", "Link DOI", "Cara ambil"])
            w.writeheader(); w.writerows(manual)
    bold("\n═══════════════════════════════════════")
    bold("  SELESAI!")
    bold("═══════════════════════════════════════")
    ok(f"Berhasil download : {ndone} PDF")
    warn(f"Perlu manual      : {len(manual)} paper")
    info(f"Semua hasil CSV   : {outdir}/hasil_pencarian.csv")
    if manual:
        info(f"List manual (+link): {outdir}/manual_download.csv")
        print("  ℹ️  Paper paywalled: buka kolom 'Link DOI' pakai akses kampus Anda.")
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

def run_extract(outdir: Path):
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

def pilih_bidang() -> dict:
    """Tanya bidang penelitian. Return preset terpilih."""
    keys = list(FIELD_PRESETS.keys())
    bold("\nBidang penelitian (biar hasilnya mengerucut):")
    for i, k in enumerate(keys, 1):
        print(f"  {i}. {FIELD_PRESETS[k]['label']}")
    print()
    default = "1"
    while True:
        p = input(f"Pilih bidang [1-{len(keys)}] [{default}]: ").strip() or default
        if p.isdigit() and 1 <= int(p) <= len(keys):
            chosen = keys[int(p) - 1]
            preset = FIELD_PRESETS[chosen]
            ok(f"Bidang: {preset['label']}")
            return preset
        warn("Pilihan tidak valid.")


def pilih_penerbit() -> dict:
    """Tanya penerbit sumber. Return preset terpilih (atau None = semua)."""
    keys = list(PUBLISHER_PRESETS.keys())
    bold("\nSumber penerbit (opsional — untuk mengerucut ke penerbit tertentu):")
    print("  0. Semua penerbit (paling luas, disarankan)")
    for i, k in enumerate(keys, 1):
        print(f"  {i}. {PUBLISHER_PRESETS[k]['label']}")
    print()
    print("  ℹ️  Catatan: PDF dari penerbit besar hanya bisa di-download otomatis")
    print("     kalau versi Open Access-nya tersedia. Sisanya masuk")
    print("     manual_download.csv untuk Anda buka via akses kampus.\n")
    default = "0"
    while True:
        p = input(f"Pilih penerbit [0-{len(keys)}] [{default}]: ").strip() or default
        if p == "0":
            ok("Penerbit: Semua penerbit")
            return None
        if p.isdigit() and 1 <= int(p) <= len(keys):
            preset = PUBLISHER_PRESETS[keys[int(p) - 1]]
            ok(f"Penerbit: {preset['label']}")
            return preset
        warn("Pilihan tidak valid.")


def menu_cari():
    """Menu: Cari & Download Jurnal."""
    bold("\n┌─────────────────────────────────────┐")
    bold("│  🔍 Cari & Download Jurnal          │")
    bold("└─────────────────────────────────────┘\n")

    print("Masukkan topik/judul penelitian yang spesifik.")
    print("Semakin spesifik, semakin relevan hasilnya.")
    print("Contoh : 'Pengaruh inflasi terhadap harga saham perbankan'")
    print("Contoh : 'Faktor yang mempengaruhi niat adopsi ChatGPT di akuntansi'")
    print("Boleh Bahasa Indonesia — otomatis diterjemahkan ke Inggris.\n")

    topik = tanya("Topik / judul penelitian")
    var_x = input("Variabel X — bebas diisi/skip (Enter untuk skip): ").strip()
    var_y = input("Variabel Y — bebas diisi/skip (Enter untuk skip): ").strip()

    field_preset = pilih_bidang()
    publisher_preset = pilih_penerbit()

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

    pakai = input("\nFilter tahun publikasi? (y/n) [n]: ").strip().lower()
    ys, ye = None, None
    if pakai == "y":
        ys = int(tanya("   Dari tahun", default=2019))
        ye = int(tanya("   Sampai tahun", default=2025))
    limit = int(tanya("Jumlah jurnal per keyword", default=10))

    print("\n" + "─" * 45)
    bold("  Ringkasan:")
    print(f"  🎯 Bidang   : {field_preset['label']}")
    print(f"  🏢 Penerbit : {publisher_preset['label'] if publisher_preset else 'Semua penerbit'}")
    print(f"  🔍 Keyword  : {', '.join(queries)}")
    if ys:
        print(f"  📅 Tahun    : {ys} – {ye}")
    print(f"  📄 Jumlah   : {limit} per keyword")
    print("  📂 Output   : " + str(DOWNLOAD_DIR))
    print("─" * 45)
    if input("\nMulai cari + download? (y/n) [y]: ").strip().lower() == "n":
        return

    print()
    outdir = run_search_download(queries, limit, ys, ye, DOWNLOAD_DIR,
                                 field_preset=field_preset,
                                 publisher_preset=publisher_preset)

    # Tawarkan ekstrak
    print("\nEkstrak ke Excel?")
    print("  - 100% offline, tanpa API key")
    print("  - Resume: PDF sudah diproses akan di-skip")
    if input("  Ekstrak sekarang? (y/n) [y]: ").strip().lower() != "n":
        run_extract(outdir)

    bold(f"\n✅ Selesai! Cek folder {outdir}/\n")

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

    run_extract(DOWNLOAD_DIR)
    bold("\n✅ Selesai!\n")

def menu_folder():
    """Menu: Ganti folder output."""
    global DOWNLOAD_DIR
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
        bold("\n╔══════════════════════════════════════════════╗")
        bold("║            📚  JURNAL FINDER                 ║")
        bold("║   Cari jurnal gratis → Download → Excel       ║")
        bold("╚══════════════════════════════════════════════╝\n")

        print(f"  📂 Folder output : {DOWNLOAD_DIR.resolve()}")
        if DOWNLOAD_DIR.exists():
            pdf_count = len(list(DOWNLOAD_DIR.glob("*.pdf")))
            print(f"  📄 PDF tersedia  : {pdf_count}")
        print()

        print("  1  🔍  Cari & Download Jurnal")
        print("  2  📊  Ekstrak PDF → Excel")
        print("  3  📁  Ganti Folder Output")
        print("  4  ❌  Keluar")
        print()

        pilihan = input("Pilih menu [1-4]: ").strip()

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
            warn("Pilihan tidak valid. Ketik angka 1-4 lalu Enter.")

def main():
    parser = argparse.ArgumentParser(
        prog="jf",
        description="📚 Jurnal Finder — cari & download jurnal ilmiah gratis.\n"
                    "Tanpa login, tanpa API key. Boleh memakai Bahasa Indonesia.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Contoh pemakaian:
  jf                                              # mode dipandu (paling mudah)
  jf --topik "pengaruh inflasi terhadap harga saham" --bidang ekonomi -n 10
  jf --keyword-en "chatgpt adoption accounting" --bidang akuntansi
  jf --topik "kecerdasan buatan" --penerbit elsevier --tahun 2020 2024
  jf --extract-only                               # ekstrak PDF yang sudah ada

Cara kerja singkat:
  1. Masukkan topik (Indonesia/Inggris) + pilih bidang + (opsional) penerbit.
  2. Tool mencari di OpenAlex, CrossRef, DOAJ, dan download PDF yang GRATIS
     (Open Access / Unpaywall), lalu memverifikasi isi PDF.
  3. Paper berbayar (paywalled) dikumpulkan di manual_download.csv berisi
     link DOI untuk Anda buka sendiri lewat akses kampus/perpustakaan.

Bidang    : ekonomi, akuntansi, manajemen, keuangan, umum
Penerbit  : elsevier, emerald, wiley, taylor-francis, springer, oxford,
            cambridge, ieee, asce, igi, jstor, sage
        """)
    parser.add_argument("--topik", default=None,
                        help="Topik/judul penelitian (boleh Bahasa Indonesia, otomatis diterjemahkan)")
    parser.add_argument("--x", default="", help="Variabel X (opsional)")
    parser.add_argument("--y", default="", help="Variabel Y (opsional)")
    parser.add_argument("--keyword-en", nargs="+", default=None,
                        help="Keyword Bahasa Inggris langsung (lewati penerjemahan)")
    parser.add_argument("--bidang", choices=list(FIELD_PRESETS.keys()), default="umum",
                        help="Bidang penelitian agar hasil mengerucut (default: umum)")
    parser.add_argument("--penerbit", choices=list(PUBLISHER_PRESETS.keys()), default=None,
                        help="Filter penerbit (default: semua penerbit)")
    parser.add_argument("-n", "--limit", type=int, default=10,
                        help="Jumlah jurnal yang diambil per keyword (default: 10)")
    parser.add_argument("--tahun", nargs=2, type=int, metavar=("DARI", "SAMPAI"), default=None,
                        help="Filter rentang tahun publikasi, mis. --tahun 2020 2024")
    parser.add_argument("--no-extract", action="store_true",
                        help="Jangan langsung ekstrak ke Excel setelah download")
    parser.add_argument("--extract-only", action="store_true",
                        help="Hanya ekstrak PDF yang sudah ada (tidak download ulang)")
    args = parser.parse_args()

    # Mode extract-only: ekstrak PDF yang sudah ada
    if args.extract_only:
        outdir = DOWNLOAD_DIR
        if not outdir.exists() or not list(outdir.glob("*.pdf")):
            err(f"Tidak ada PDF di {outdir}")
            print("  Jalankan 'jf' tanpa argumen, lalu pilih menu 'Cari & Download'.")
            return
        run_extract(outdir)
        return

    # Tanpa topik/keyword → mode dipandu interaktif
    if not args.topik and not args.keyword_en:
        interactive()
        return

    field_preset = FIELD_PRESETS[args.bidang]
    publisher_preset = PUBLISHER_PRESETS[args.penerbit] if args.penerbit else None
    queries = args.keyword_en or []
    if args.topik and not args.keyword_en:
        print("🌐 Menerjemahkan topik ke Inggris...")
        te, _ = translate_id_en(args.topik)
        xe, _ = translate_id_en(args.x) if args.x else ("", "")
        ye, _ = translate_id_en(args.y) if args.y else ("", "")
        queries = list(dict.fromkeys(q for q in [te, f"{xe} {ye}".strip()] if q))
        info(f"'{args.topik}' → {queries}")
    if not queries:
        err("Topik kosong. Isi --topik atau --keyword-en.")
        return
    ys, ye = (args.tahun[0], args.tahun[1]) if args.tahun else (None, None)
    if ys and ye and ys > ye:
        warn("Tahun 'DARI' lebih besar dari 'SAMPAI'. Rentang ditukar otomatis.")
        ys, ye = ye, ys
    print(f"\n🎯 Bidang   : {field_preset['label']}")
    print(f"🏢 Penerbit : {publisher_preset['label'] if publisher_preset else 'Semua penerbit'}")
    print(f"📂 Output   : {DOWNLOAD_DIR}\n")
    outdir = run_search_download(queries, args.limit, ys, ye, DOWNLOAD_DIR,
                                 field_preset=field_preset,
                                 publisher_preset=publisher_preset)
    if not args.no_extract:
        print("\nEkstrak ke Excel? (otomatis; pakai --no-extract untuk lewati)")
        run_extract(outdir)

if __name__ == "__main__":
    main()
