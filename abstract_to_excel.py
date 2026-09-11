#!/usr/bin/env python3
"""
abstract_to_excel.py - Baca abstrak jurnal PDF → Excel perbandingan otomatis
Pake OpenRouter (DeepSeek free) untuk extract: judul, penulis, tahun, X, Y, metode, hasil
"""

import os
import json
import time
import argparse
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Config ───────────────────────────────────────────────────────────────────
PDF_DIR          = Path("./jurnal_download")
OUTPUT_XLSX      = Path("./jurnal_download/tabel_perbandingan.xlsx")
OPENROUTER_API   = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY", "")  # set env atau isi langsung di sini
MAX_CHARS        = 4000

# ── Colors ───────────────────────────────────────────────────────────────────
class C:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def ok(msg):   print(f"{C.GREEN}✓{C.RESET} {msg}")
def warn(msg): print(f"{C.YELLOW}⚠{C.RESET} {msg}")
def err(msg):  print(f"{C.RED}✗{C.RESET} {msg}")
def info(msg): print(f"{C.CYAN}→{C.RESET} {msg}")
def bold(msg): print(f"{C.BOLD}{msg}{C.RESET}")

# ── Extract teks dari PDF ────────────────────────────────────────────────────
def extract_pdf_text(pdf_path: Path, max_chars: int = MAX_CHARS) -> str:
    # pdftotext (paling akurat, butuh poppler)
    try:
        import subprocess
        result = subprocess.run(
            ["pdftotext", "-f", "1", "-l", "3", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30
        )
        text = result.stdout.strip()
        if text:
            return text[:max_chars]
    except Exception:
        pass

    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        text = ""
        for page in reader.pages[:3]:
            text += page.extract_text() or ""
            if len(text) >= max_chars:
                break
        if text.strip():
            return text[:max_chars]
    except Exception:
        pass

    # Fallback: pdfminer
    try:
        from pdfminer.high_level import extract_text as pm_extract  # type: ignore[import-not-found]
        text = pm_extract(str(pdf_path), maxpages=3)
        return text[:max_chars]
    except Exception:
        return ""

# ── Parse jurnal via OpenRouter DeepSeek ─────────────────────────────────────
def parse_with_deepseek(text: str, filename: str) -> dict:
    if not OPENROUTER_KEY:
        err("OPENROUTER_API_KEY belum di-set! Set env var atau isi di config.")
        return _fallback_entry(filename)

    prompt = f"""Kamu adalah research assistant. Berikut teks dari jurnal akademik (halaman 1-3):

FILENAME: {filename}
---
{text}
---

Extract informasi berikut dalam format JSON. Jika tidak ditemukan, isi dengan "-".
Istilah teknis boleh dalam bahasa Inggris, penjelasan dalam Bahasa Indonesia.

{{
  "judul": "judul lengkap jurnal",
  "penulis": "Nama1, Nama2 et al. (maks 3 nama)",
  "tahun": "tahun publikasi (angka saja)",
  "jurnal": "nama jurnal/publikasi",
  "variabel_x": "variabel independen utama (singkat, pisah koma jika lebih dari 1)",
  "variabel_y": "variabel dependen (biasanya Firm Value / Tobin's Q)",
  "variabel_kontrol": "variabel kontrol (singkat, pisah koma)",
  "metode": "metode analisis (contoh: Panel Data FE, GMM, OLS, Path Analysis)",
  "hasil": "kesimpulan: apakah X berpengaruh positif/negatif/tidak signifikan terhadap Y",
  "teori": "teori yang digunakan (contoh: Signaling Theory, Stakeholder Theory)",
  "sampel": "populasi/sampel penelitian (contoh: Perusahaan LQ45 BEI 2018-2022)"
}}

Balas HANYA dengan JSON valid. Tanpa penjelasan, tanpa markdown, tanpa kode blok."""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/skripsi-jurnal-dl",
        "X-Title": "Skripsi Journal Analyzer",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "max_tokens": 1000,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}]
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(OPENROUTER_API, headers=headers, json=payload, timeout=60)
            if resp.status_code == 429:
                wait = 15 * (attempt + 1)
                warn(f"Rate limited, tunggu {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            raw  = data["choices"][0]["message"]["content"].strip()
            raw  = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except json.JSONDecodeError:
            warn(f"JSON parse error untuk {filename}")
            return _fallback_entry(filename)
        except Exception as e:
            err(f"API error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    return _fallback_entry(filename)

def _fallback_entry(filename: str) -> dict:
    return {
        "judul": filename, "penulis": "-", "tahun": "-", "jurnal": "-",
        "variabel_x": "-", "variabel_y": "Firm Value (Tobin's Q)",
        "variabel_kontrol": "-", "metode": "-",
        "hasil": "-", "teori": "-", "sampel": "-"
    }

# ── Buat Excel ────────────────────────────────────────────────────────────────
def build_excel(entries: list, output_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Tabel Jurnal"

    # Styles
    hdr_fill  = PatternFill("solid", start_color="1F4E79")
    alt_fill  = PatternFill("solid", start_color="EBF3FB")
    wht_fill  = PatternFill("solid", start_color="FFFFFF")
    sub_fill  = PatternFill("solid", start_color="2E75B6")
    hdr_font  = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    sub_font  = Font(name="Arial", bold=True, color="FFFFFF", size=9)
    body_font = Font(name="Arial", size=9)
    center    = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_wrap = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    thin      = Side(style="thin", color="BFBFBF")
    border    = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Title
    ws.merge_cells("A1:K1")
    ws["A1"] = "TABEL PERBANDINGAN LITERATUR — ESG & NILAI PERUSAHAAN (TOBIN'S Q)"
    ws["A1"].font      = Font(name="Arial", bold=True, size=12, color="1F4E79")
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 24

    ws.merge_cells("A2:K2")
    ws["A2"] = f"Y (Dependen): Nilai Perusahaan / Firm Value (Tobin's Q)  |  Total: {len(entries)} jurnal"
    ws["A2"].font      = Font(name="Arial", size=9, italic=True, color="595959")
    ws["A2"].alignment = center
    ws.row_dimensions[2].height = 16

    # Header columns
    cols = [
        ("No",             5),  ("Judul",        38), ("Penulis",   18),
        ("Tahun",          7),  ("Jurnal",        20), ("Variabel X", 22),
        ("Variabel Y",    18),  ("Kontrol",       18), ("Metode",    18),
        ("Hasil / Temuan", 28), ("Teori & Sampel", 22),
    ]
    ws.row_dimensions[3].height = 28
    for col, (label, width) in enumerate(cols, 1):
        cell = ws.cell(row=3, column=col, value=label)
        cell.font = hdr_font; cell.fill = hdr_fill
        cell.alignment = center; cell.border = border
        ws.column_dimensions[get_column_letter(col)].width = width

    # Data rows
    for i, e in enumerate(entries, 1):
        row  = i + 3
        fill = alt_fill if i % 2 == 0 else wht_fill
        teori_sampel = "\n".join(filter(lambda s: s != "-", [
            e.get("teori", "-"), e.get("sampel", "-")
        ])) or "-"
        values = [
            i, e.get("judul","-"), e.get("penulis","-"), e.get("tahun","-"),
            e.get("jurnal","-"), e.get("variabel_x","-"), e.get("variabel_y","-"),
            e.get("variabel_kontrol","-"), e.get("metode","-"),
            e.get("hasil","-"), teori_sampel,
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.font = body_font; cell.fill = fill; cell.border = border
            cell.alignment = center if col in (1, 4) else left_wrap
        ws.row_dimensions[row].height = 60

    ws.freeze_panes = "B4"

    # Sheet 2: Gap Analysis
    ws2 = wb.create_sheet("Analisis Gap X")
    ws2["A1"] = "ANALISIS VARIABEL X — FREKUENSI & GAP PENELITIAN"
    ws2["A1"].font = Font(name="Arial", bold=True, size=11, color="1F4E79")
    ws2.row_dimensions[1].height = 20

    for col, h in enumerate(["Variabel X", "Jumlah Jurnal", "Catatan"], 1):
        cell = ws2.cell(row=2, column=col, value=h)
        cell.font = sub_font; cell.fill = sub_fill
        cell.alignment = center; cell.border = border
    ws2.column_dimensions["A"].width = 35
    ws2.column_dimensions["B"].width = 15
    ws2.column_dimensions["C"].width = 45

    from collections import Counter
    all_x = []
    for e in entries:
        for x in (e.get("variabel_x") or "").split(","):
            x = x.strip()
            if x and x != "-":
                all_x.append(x)

    for i, (x_var, count) in enumerate(Counter(all_x).most_common(), 1):
        row  = i + 2
        fill = alt_fill if i % 2 == 0 else wht_fill
        note = "✓ X utama kamu" if "ESG" in x_var.upper() else "→ Peluang / variabel tambahan"
        for col, val in enumerate([x_var, count, note], 1):
            cell = ws2.cell(row=row, column=col, value=val)
            cell.font = body_font; cell.fill = fill
            cell.border = border; cell.alignment = left_wrap
        ws2.row_dimensions[row].height = 18

    ws2.freeze_panes = "A3"
    wb.save(str(output_path))

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="📊 Extract abstrak jurnal PDF → Excel (via OpenRouter DeepSeek)",
        epilog="Contoh:\n  python abstract_to_excel.py\n  python abstract_to_excel.py --dir ./jurnal_download --out hasil.xlsx"
    )
    parser.add_argument("--dir",     default=str(PDF_DIR),    help="Folder PDF")
    parser.add_argument("--out",     default=str(OUTPUT_XLSX), help="Output Excel")
    parser.add_argument("--api-key", default=None,             help="OpenRouter API key")
    args = parser.parse_args()

    global OPENROUTER_KEY
    if args.api_key:
        OPENROUTER_KEY = args.api_key

    if not OPENROUTER_KEY:
        err("API key tidak ditemukan!")
        err("Set via: export OPENROUTER_API_KEY=sk-or-xxxx")
        err("Atau:    python abstract_to_excel.py --api-key sk-or-xxxx")
        return

    pdf_dir     = Path(args.dir)
    output_path = Path(args.out)
    pdf_files   = sorted(pdf_dir.glob("*.pdf"))

    bold("\n═══════════════════════════════════════════")
    bold("  📊 Abstract → Excel  (DeepSeek via OpenRouter)")
    bold("═══════════════════════════════════════════\n")
    info(f"Model  : {OPENROUTER_MODEL}")
    info(f"Folder : {pdf_dir}")
    print()

    if not pdf_files:
        err(f"Tidak ada PDF di {pdf_dir}")
        return

    info(f"Ditemukan {len(pdf_files)} PDF\n")

    entries = []
    for i, pdf in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] {pdf.name[:65]}...")
        text = extract_pdf_text(pdf)
        if not text:
            warn("Gagal extract teks, skip")
            entries.append(_fallback_entry(pdf.name))
            continue
        ok(f"Teks terekstrak ({len(text)} chars)")
        info("Parsing dengan DeepSeek...")
        entry = parse_with_deepseek(text, pdf.name)
        entries.append(entry)
        ok(f"Done: {entry.get('judul','')[:60]}")
        print()
        time.sleep(1)

    info("Membuat Excel...")
    build_excel(entries, output_path)

    bold("\n═══════════════════════════════════════════")
    bold("  SELESAI!")
    bold("═══════════════════════════════════════════")
    ok(f"Berhasil proses : {len(entries)} jurnal")
    info(f"Output          : {output_path}\n")

if __name__ == "__main__":
    main()
