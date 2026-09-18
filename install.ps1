# ═══════════════════════════════════════════════════════════════════════════
# Jurnal Finder — installer satu-baris (Windows / PowerShell)
#
# Cara pakai (satu baris di PowerShell):
#   irm https://raw.githubusercontent.com/Nomssky/jurnal-finder/main/install.ps1 | iex
#
# Skrip ini mengunduh install.bat resmi dari repo lalu menjalankannya,
# sehingga hanya ada satu sumber kebenaran untuk logika instalasi Windows.
# ═══════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"

$repoRaw = if ($env:JF_REPO_RAW) { $env:JF_REPO_RAW } else { "https://raw.githubusercontent.com/Nomssky/jurnal-finder/main" }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          📚  JURNAL FINDER — Installer        ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$tmpBat = Join-Path $env:TEMP "jf_install.bat"

try {
    Write-Host "→ Mengunduh installer..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "$repoRaw/install.bat" -OutFile $tmpBat -UseBasicParsing
} catch {
    Write-Host "✗ Gagal mengunduh installer. Periksa koneksi internet." -ForegroundColor Red
    Write-Host "  URL: $repoRaw/install.bat" -ForegroundColor Red
    exit 1
}

Write-Host "→ Menjalankan installer..." -ForegroundColor Cyan
Write-Host ""
& cmd.exe /c $tmpBat
