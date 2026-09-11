#!/usr/bin/env python3
"""
journal_dl.py - Bulk Journal Downloader for Skripsi
Searches Semantic Scholar + checks Unpaywall for free PDFs
"""

import os
import sys
import time
import csv
import argparse
import requests
from pathlib import Path
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
UNPAYWALL_API        = "https://api.unpaywall.org/v2/{doi}"
UNPAYWALL_EMAIL      = "als.kresna@email.com"  # ganti dengan email kamu
DOWNLOAD_DIR         = Path("./jurnal_download")
RESULTS_CSV          = "hasil_pencarian.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (journal-downloader-skripsi/1.0)"}
S2_API_KEY = ""  # optional: isi kalau punya, https://www.semanticscholar.org/product/api

# ── Colors (biar CLI nya enak dibaca) ──────────────────────────────────────
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

# ── Search Semantic Scholar ─────────────────────────────────────────────────
def search_papers(keyword: str, limit: int = 20, year_start: int = None, year_end: int = None) -> list:
    info(f"Mencari: '{keyword}' ...")

    params = {
        "query": keyword,
        "limit": limit,
        "fields": "title,authors,year,externalIds,openAccessPdf,abstract,citationCount,publicationTypes,journal"
    }
    if year_start and year_end:
        params["year"] = f"{year_start}-{year_end}"
    elif year_start:
        params["year"] = f"{year_start}-"

    headers = dict(HEADERS)
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    max_retries = 5
    for attempt in range(max_retries):
        try:
            resp = requests.get(SEMANTIC_SCHOLAR_API, params=params, headers=headers, timeout=15)
            if resp.status_code == 429:
                wait = 15 * (2 ** attempt)  # 15s, 30s, 60s, 120s, 240s
                warn(f"Rate limited. Tunggu {wait}s lalu retry ({attempt+1}/{max_retries})...")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                err(f"HTTP {resp.status_code} untuk '{keyword}'")
                return []
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            ok(f"Ditemukan {len(papers)} paper")
            return papers
        except requests.exceptions.RequestException as e:
            err(f"Gagal search: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            continue
    err(f"Menyerah setelah {max_retries} percobaan untuk: '{keyword}'")
    return []

# ── Cek Unpaywall untuk PDF gratis ─────────────────────────────────────────
def get_free_pdf_url(doi: str) -> str | None:
    if not doi:
        return None
    try:
        url = UNPAYWALL_API.format(doi=doi)
        resp = requests.get(url, params={"email": UNPAYWALL_EMAIL}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("is_oa"):
                best = data.get("best_oa_location", {})
                return best.get("url_for_pdf") or best.get("url")
    except Exception:
        pass
    return None

# ── Download PDF ────────────────────────────────────────────────────────────
def download_pdf(url: str, filename: str) -> bool:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and "octet-stream" not in content_type:
            # Coba tetap download, mungkin headernya salah
            pass
        
        filepath = DOWNLOAD_DIR / filename
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Validasi minimal: cek magic bytes PDF
        with open(filepath, "rb") as f:
            header = f.read(4)
        if header != b"%PDF":
            os.remove(filepath)
            return False
            
        return True
    except Exception as e:
        return False

# ── Sanitize filename ───────────────────────────────────────────────────────
def safe_filename(title: str, year: int = None, max_len: int = 80) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")
    name = "".join(c if c in keep else "_" for c in (title or ""))
    name = name[:max_len].strip()
    if not name:
        name = "untitled"
    if year:
        name = f"[{year}] {name}"
    return name + ".pdf"

# ── Main Logic ──────────────────────────────────────────────────────────────
def run(keywords: list[str], limit: int, year_start: int, year_end: int, email: str):
    global UNPAYWALL_EMAIL
    if email:
        UNPAYWALL_EMAIL = email

    DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    all_papers = []
    seen_ids = set()

    bold("\n═══════════════════════════════════════")
    bold("  📚 Journal Bulk Downloader - Skripsi ")
    bold("═══════════════════════════════════════\n")

    # Kumpulkan semua hasil search
    for kw in keywords:
        papers = search_papers(kw, limit=limit, year_start=year_start, year_end=year_end)
        for p in papers:
            pid = p.get("paperId")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_papers.append(p)
        time.sleep(5)  # Rate limit friendly — jeda 5s antar keyword

    bold(f"\nTotal unik: {len(all_papers)} paper\n")

    # Proses tiap paper
    results = []
    downloaded = 0
    manual_list = []

    for i, paper in enumerate(all_papers, 1):
        title       = paper.get("title", "Untitled")
        year        = paper.get("year")
        authors     = ", ".join(a["name"] for a in paper.get("authors", [])[:3])
        doi         = paper.get("externalIds", {}).get("DOI")
        citation    = paper.get("citationCount", 0)
        oa_pdf      = paper.get("openAccessPdf", {})
        direct_url  = oa_pdf.get("url") if oa_pdf else None

        print(f"[{i}/{len(all_papers)}] {title[:70]}...")

        # Cari URL PDF
        pdf_url = direct_url
        source  = "Semantic Scholar (OA)"

        if not pdf_url and doi:
            pdf_url = get_free_pdf_url(doi)
            source  = "Unpaywall"
            time.sleep(0.5)

        status = "❌ Manual"
        if pdf_url:
            filename = safe_filename(title, year)
            success  = download_pdf(pdf_url, filename)
            if success:
                ok(f"Downloaded → {filename}")
                status = "✅ Downloaded"
                downloaded += 1
            else:
                warn(f"URL ada tapi gagal download")
                manual_list.append({"title": title, "doi": doi, "year": year})
        else:
            warn(f"Tidak ada PDF gratis → masuk list manual")
            manual_list.append({"title": title, "doi": doi, "year": year})

        results.append({
            "No"         : i,
            "Title"      : title,
            "Authors"    : authors,
            "Year"       : year,
            "DOI"        : doi or "-",
            "Citations"  : citation,
            "Status"     : status,
            "Source"     : source if "Downloaded" in status else "-",
        })

    # ── Guard: tidak ada hasil sama sekali ─────────────────────────────────
    if not results:
        err("Tidak ada paper yang ditemukan. Coba keyword lain atau cek koneksi.")
        return

    # ── Export CSV ──────────────────────────────────────────────────────────
    csv_path = DOWNLOAD_DIR / RESULTS_CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    # Export list manual
    if manual_list:
        manual_path = DOWNLOAD_DIR / "manual_download.csv"
        with open(manual_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "doi", "year"])
            writer.writeheader()
            writer.writerows(manual_list)

    # ── Summary ─────────────────────────────────────────────────────────────
    bold("\n═══════════════════════════════════════")
    bold("  SELESAI!")
    bold("═══════════════════════════════════════")
    ok(f"Berhasil download : {downloaded} PDF")
    warn(f"Perlu manual      : {len(manual_list)} paper")
    info(f"Semua hasil CSV   : {csv_path}")
    if manual_list:
        info(f"List manual       : {DOWNLOAD_DIR}/manual_download.csv")
    info(f"PDF tersimpan di  : {DOWNLOAD_DIR}/\n")

    if manual_list:
        print(f"{C.YELLOW}Tip: Untuk yang manual, pakai akses Scopus/ScienceDirect Undip,")
        print(f"     lalu search by DOI yang ada di manual_download.csv{C.RESET}\n")

# ── CLI Entry Point ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="📚 Bulk download jurnal untuk skripsi",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Contoh penggunaan:
  python journal_dl.py -k "machine learning" "deep learning"
  python journal_dl.py -k "supply chain" -n 30 -y 2020 2024
  python journal_dl.py -k "sentiment analysis" -n 50 -e kamu@email.com
        """
    )
    parser.add_argument(
        "-k", "--keywords", nargs="+", required=True,
        help="Keyword pencarian (bisa lebih dari satu)"
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=20,
        help="Jumlah paper per keyword (default: 20)"
    )
    parser.add_argument(
        "-y", "--year", nargs=2, type=int, metavar=("START", "END"),
        help="Filter tahun, contoh: -y 2020 2024"
    )
    parser.add_argument(
        "-e", "--email", type=str, default=None,
        help="Email untuk Unpaywall API (gratis, makin akurat)"
    )

    parser.add_argument(
        "--api-key", type=str, default=None,
        help="Semantic Scholar API key (opsional, hilangkan rate limit)"
    )

    args = parser.parse_args()
    if args.api_key:
        global S2_API_KEY
        S2_API_KEY = args.api_key
    year_start, year_end = (args.year[0], args.year[1]) if args.year else (None, None)

    run(
        keywords   = args.keywords,
        limit      = args.limit,
        year_start = year_start,
        year_end   = year_end,
        email      = args.email
    )

# ── Interactive Mode ─────────────────────────────────────────────────────────
def tanya(pertanyaan: str, default=None) -> str:
    if default:
        jawaban = input(f"{pertanyaan} [{default}]: ").strip()
        return jawaban if jawaban else str(default)
    while True:
        jawaban = input(f"{pertanyaan}: ").strip()
        if jawaban:
            return jawaban
        print("  ⚠ Tidak boleh kosong, coba lagi.")

def interactive():
    bold("\n╔══════════════════════════════════════════╗")
    bold("║   📚 Journal Finder untuk Skripsi        ║")
    bold("╚══════════════════════════════════════════╝\n")

    print("Halo! Aku bantu cariin jurnal buat skripsi kamu.\n")

    # ── Topik / Y ────────────────────────────────────────────────────────────
    print("1️⃣  Pertama, ceritain topik skripsi kamu.")
    print("   Contoh: 'pengaruh ESG terhadap nilai perusahaan'")
    print("           'hubungan inflasi dan harga saham'")
    topik = tanya("   Topik skripsi kamu")

    # ── Keyword tambahan ─────────────────────────────────────────────────────
    print(f"\n2️⃣  Selain '{topik}', ada kata kunci lain yang mau dicari?")
    print("   Pisah pakai koma. Kosongkan kalau cukup topik di atas.")
    print("   Contoh: 'firm value, Tobin Q, IDX80'")
    tambahan = input("   Keyword tambahan (Enter untuk skip): ").strip()

    keywords = [topik]
    if tambahan:
        keywords += [k.strip() for k in tambahan.split(",") if k.strip()]

    # ── Tahun ────────────────────────────────────────────────────────────────
    print("\n3️⃣  Mau filter tahun terbit jurnal?")
    print("   Rekomendasi buat skripsi: 5-10 tahun terakhir (2015-2024)")
    pakai_tahun = input("   Filter tahun? (y/n) [y]: ").strip().lower()
    year_start, year_end = None, None
    if pakai_tahun != "n":
        year_start = int(tanya("   Dari tahun", default=2018))
        year_end   = int(tanya("   Sampai tahun", default=2024))

    # ── Jumlah ───────────────────────────────────────────────────────────────
    print("\n4️⃣  Mau cari berapa jurnal per keyword?")
    print("   Makin banyak makin lama, tapi makin lengkap.")
    limit = int(tanya("   Jumlah jurnal per keyword", default=20))

    # ── Email ────────────────────────────────────────────────────────────────
    print("\n5️⃣  Email kamu? (buat akses lebih banyak PDF gratis)")
    print("   Pakai email kampus kalau ada, contoh: nama@students.undip.ac.id")
    email = tanya("   Email kamu", default="user@email.com")

    # ── Konfirmasi ───────────────────────────────────────────────────────────
    print("\n" + "─"*45)
    bold("  Ringkasan pencarian:")
    print(f"  🔍 Keyword : {', '.join(keywords)}")
    if year_start:
        print(f"  📅 Tahun   : {year_start} – {year_end}")
    print(f"  📄 Jumlah  : {limit} per keyword")
    print(f"  📧 Email   : {email}")
    print("─"*45)

    lanjut = input("\nLanjut cari jurnal? (y/n) [y]: ").strip().lower()
    if lanjut == "n":
        print("Oke, dibatalin. Jalanin lagi kalau udah siap!")
        return

    print()
    run(keywords=keywords, limit=limit, year_start=year_start,
        year_end=year_end, email=email)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        interactive()