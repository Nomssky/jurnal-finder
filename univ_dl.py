#!/usr/bin/env python3
"""
univ_dl.py - Bulk download PDF jurnal bermodal akun universitas (SSO).

Kenapa script ini ada:
- API key Elsevier hanya untuk SEARCH metadata, BUKAN untuk membuka PDF paywall.
- PDF paywall butuh bukti "warga institusi berlangganan". Di browser buktinya adalah
  login SSO; di script buktinya adalah cookie sesi hasil login SSO tersebut.
- Alur: login manual SEKALI di browser sungguhan (kamu yang mengetik password SSO
  sendiri — script tidak pernah melihat, meminta, atau menyimpan password) ->
  cookie sesi disimpan di file lokal -> mode download memakai cookie itu.

Pakai:
  python univ_dl.py login
  python univ_dl.py download -f jurnal_download/manual_download.csv
  python univ_dl.py download --doi 10.1016/j.jbankfin.2019.01.001 10.1016/j.xxx
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────
SESSION_FILE  = Path("./.session_sciencedirect.json")
LOGIN_URL     = "https://www.sciencedirect.com/"
DOWNLOAD_DIR  = Path("./jurnal_download")
HEADERS = {"User-Agent": "Mozilla/5.0 (journal-downloader-skripsi/1.0)"}

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

# ── Session handling ───────────────────────────────────────────────────────
def load_session() -> requests.Session | None:
    """Bangun requests.Session dari cookie file sesi Playwright. None kalau belum login."""
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
            session.cookies.set(
                c["name"], c.get("value", ""),
                domain=c.get("domain", ""), path=c.get("path", "/"),
            )
        except Exception:
            continue
    if not session.cookies:
        return None
    return session

def looks_like_login_wall(resp: requests.Response) -> bool:
    """True jika respons malah halaman login/SSO (sesi habis / tidak berlaku)."""
    url = (getattr(resp, "url", "") or "").lower()
    if resp.status_code in (401, 403):
        return True
    for marker in ("login", "signin", "sign-in", "sso", "shibboleth", "authenticate"):
        if marker in url:
            return True
    return False

# ── Mode: login ────────────────────────────────────────────────────────────
def cmd_login():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        err("playwright belum terinstall. Jalankan:")
        err("  pip install -r requirements.txt && python -m playwright install chromium")
        return
    bold("\n═══════════════════════════════════════")
    bold("  🔑 Login institusi (sekali saja)")
    bold("═══════════════════════════════════════\n")
    print("Browser akan terbuka. Langkah kamu:")
    print("  1. Klik Sign in → Sign in via your institution → cari UNDIP")
    print("  2. Login SSO UNDIP seperti biasa (kamu yang ketik password sendiri)")
    print("  3. Pastikan halaman ScienceDirect terbuka sebagai user institusi")
    print("  4. Kembali ke terminal ini, tekan ENTER\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        input("Kalau sudah login di browser, tekan ENTER di sini... ")
        ctx.storage_state(path=str(SESSION_FILE))
        browser.close()
    session = load_session()
    if session:
        ok(f"Sesi tersimpan di {SESSION_FILE} ({len(session.cookies)} cookie)")
        info("JANGAN commit/upload file ini — ini kunci akses institusimu.")
    else:
        err("Gagal menyimpan sesi (tidak ada cookie). Ulangi login.")

# ── Resolve DOI → URL PDF ScienceDirect ────────────────────────────────────
def resolve_sd_pdf_url(doi: str, session: requests.Session) -> tuple[str | None, str]:
    """Ikuti DOI; kalau mendarat di artikel ScienceDirect, kembalikan URL PDF-nya.
    Return (pdf_url, status): status = 'ok' | 'login' | 'nonsd' | 'error'."""
    try:
        resp = session.get(f"https://doi.org/{doi}", timeout=30, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        return None, f"error: {e}"
    if looks_like_login_wall(resp):
        return None, "login"
    final = (getattr(resp, "url", "") or "").split("?")[0].rstrip("/")
    if "sciencedirect.com/science/article/pii/" not in final:
        return None, "nonsd"
    pdf_url = final + "/pdfft?isDTMRedir=true&download=true"
    return pdf_url, "ok"

def download_pdf_with_session(pdf_url: str, session: requests.Session, filepath: Path) -> str:
    """Return 'ok' | 'login' | 'fail'."""
    try:
        resp = session.get(pdf_url, timeout=60, stream=True)
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
            header = f.read(4)
        if header != b"%PDF":
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
    if year:
        name = f"[{year}] {name}"
    return name + ".pdf"

def read_dois_from_csv(csv_path: Path) -> list[dict]:
    """Baca kolom title/doi/year/link (case-insensitive) dari manual_download.csv."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        for r in reader:
            doi = (r.get(cols.get("doi", "doi"), "") or "").strip()
            if not doi or doi == "-":
                continue
            rows.append({
                "title": (r.get(cols.get("title", "title"), "") or "").strip() or doi,
                "doi": doi,
                "year": (r.get(cols.get("year", "year"), "") or "").strip() or None,
            })
    return rows

# ── Mode: download ─────────────────────────────────────────────────────────
def cmd_download(dois: list[dict], outdir: Path):
    session = load_session()
    if session is None:
        err(f"Belum login. Jalankan dulu: python {Path(__file__).name} login")
        return
    outdir.mkdir(parents=True, exist_ok=True)
    bold("\n═══════════════════════════════════════")
    bold("  📥 Bulk download via sesi institusi")
    bold("═══════════════════════════════════════\n")
    results, ndone, expired = [], 0, False
    for i, item in enumerate(dois, 1):
        doi, title = item["doi"], item["title"]
        print(f"[{i}/{len(dois)}] {title[:65]}...")
        pdf_url, status = resolve_sd_pdf_url(doi, session)
        if status == "login":
            err("Sesi habis / tidak berlaku. Jalankan 'login' ulang.")
            expired = True
            results.append({**item, "status": "session-expired"})
            break
        if status != "ok":
            warn(f"Terlewat ({status}: bukan artikel ScienceDirect / gagal resolve)")
            results.append({**item, "status": f"skip-{status}"})
            continue
        filepath = outdir / safe_filename(title, item.get("year"))
        dl = download_pdf_with_session(pdf_url, session, filepath)
        if dl == "ok":
            ok(f"Downloaded → {filepath.name}")
            results.append({**item, "status": "downloaded", "file": filepath.name})
            ndone += 1
        elif dl == "login":
            err("Sesi habis / tidak berlaku. Jalankan 'login' ulang.")
            expired = True
            results.append({**item, "status": "session-expired"})
            break
        else:
            warn("Gagal ambil PDF (mungkin tidak dilanggan institusi)")
            results.append({**item, "status": "failed"})
        time.sleep(1)
    csv_path = outdir / "hasil_download_univ.csv"
    if results:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
    bold("\n═══════════════════════════════════════")
    bold("  SELESAI!")
    bold("═══════════════════════════════════════")
    ok(f"Berhasil download : {ndone} PDF")
    if expired:
        warn("Sesi berakhir di tengah jalan — yang belum kedownload, ulangi setelah login lagi.")
    info(f"Hasil CSV         : {csv_path}\n")

# ── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="📥 Bulk download PDF jurnal bermodal akun universitas (SSO via browser)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Contoh:
  python univ_dl.py login
  python univ_dl.py download -f jurnal_download/manual_download.csv
  python univ_dl.py download --doi 10.1016/j.jbankfin.2019.01.001
        """,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Login SSO manual sekali via browser, simpan sesi")
    dl = sub.add_parser("download", help="Download banyak PDF pakai sesi tersimpan")
    dl.add_argument("-f", "--csv", default=None, help="CSV berisi kolom doi (mis. manual_download.csv)")
    dl.add_argument("--doi", nargs="+", default=None, help="Daftar DOI langsung")
    dl.add_argument("-o", "--out", default=str(DOWNLOAD_DIR), help="Folder output")
    args = parser.parse_args()

    if args.cmd == "login":
        cmd_login()
    elif args.cmd == "download":
        items: list[dict] = []
        if args.csv:
            items += read_dois_from_csv(Path(args.csv))
        if args.doi:
            items += [{"title": d, "doi": d, "year": None} for d in args.doi]
        if not items:
            err("Tidak ada DOI. Pakai -f file.csv atau --doi 10.xxxx/xxxx ...")
            return
        cmd_download(items, Path(args.out))

if __name__ == "__main__":
    main()
