@echo off
:: ═══════════════════════════════════════════════════════════════════════════
:: Jurnal Finder - installer otomatis (Windows)
::
:: Cara pakai paling mudah (satu baris di PowerShell):
::   irm https://raw.githubusercontent.com/Nomssky/jurnal-finder/main/install.ps1 | iex
::
:: Atau kalau repo sudah ada di komputer, klik dua kali install.bat ini.
::
:: Installer otomatis: cek Python 3.10+ (coba pasang bila belum ada),
:: unduh kode, buat lingkungan, pasang dependensi, daftarkan perintah `jf`.
:: ═══════════════════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "INSTALL_DIR=%USERPROFILE%\.jf"
if defined JF_INSTALL_DIR set "INSTALL_DIR=%JF_INSTALL_DIR%"
set "REPO_URL=https://github.com/Nomssky/jurnal-finder.git"
if defined JF_REPO_URL set "REPO_URL=%JF_REPO_URL%"
set "BIN_DIR=%USERPROFILE%\.local\bin"

echo.
echo ================================================
echo           JURNAL FINDER - Installer
echo    Cari jurnal gratis -^> Download -^> Excel
echo ================================================
echo.

:: ── Pastikan Python 3.10+ ───────────────────────────────────────────────────
set "PY="
call :find_python
if not defined PY (
    echo [!] Python 3.10+ belum ada - mencoba memasang otomatis...
    where winget >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo     Memasang Python via winget...
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    )
    call :find_python
)
if not defined PY (
    echo.
    echo [X] Gagal menyiapkan Python 3.10+ secara otomatis.
    echo.
    echo     Silakan pasang Python dulu, lalu jalankan installer ini lagi:
    echo       1. Buka https://www.python.org/downloads/
    echo       2. Unduh Python 3.10 atau lebih baru
    echo       3. PENTING: centang "Add Python to PATH" saat memasang
    echo       4. Tutup jendela ini, buka baru, lalu ulangi install
    echo.
    echo     Tips: instalasi termudah lewat Microsoft Store, cari "Python 3.12".
    echo.
    pause
    exit /b 1
)
echo [OK] Python ditemukan.

:: ── Unduh kode sumber ───────────────────────────────────────────────────────
echo.
echo [*] Menyiapkan kode Jurnal Finder...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: 1) Pakai folder ini bila ada pyproject.toml (install.bat dijalankan dari repo)
if exist "%~dp0pyproject.toml" (
    if /i not "%~dp0"=="%INSTALL_DIR%\" (
        echo     Menyalin dari folder ini...
        where robocopy >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            robocopy "%~dp0." "%INSTALL_DIR%" /E ^
                /XD .git .venv venv build dist .opencode node_modules __pycache__ .mypy_cache .pytest_cache *.egg-info ^
                /XF *.pyc /NFL /NDL /NJH /NJS /NP >nul
            if !ERRORLEVEL! GEQ 8 ( echo [X] Copy gagal. & pause & exit /b 1 )
        ) else (
            xcopy "%~dp0*" "%INSTALL_DIR%\" /E /I /H /Y /Q >nul
        )
    ) else (
        echo     Repo sudah berada di %INSTALL_DIR%
    )
) else (
    :: 2) git clone bila git tersedia
    where git >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        if exist "%INSTALL_DIR%\.git" (
            echo     Memperbarui repo...
            git -C "%INSTALL_DIR%" pull --quiet
        ) else (
            echo     Mengunduh via git...
            git clone --depth 1 "%REPO_URL%" "%INSTALL_DIR%"
        )
    ) else (
        :: 3) Unduh zip tanpa git (butuh PowerShell yang selalu ada di Windows)
        echo     Git tidak ada - mengunduh via PowerShell...
        if exist "%INSTALL_DIR%\.git" rmdir /s /q "%INSTALL_DIR%\.git" >nul 2>&1
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "$u='%REPO_URL%'.Replace('.git','');" ^
            "$z=Join-Path $env:TEMP 'jf.zip';" ^
            "Invoke-WebRequest -Uri \"$u/archive/refs/heads/main.zip\" -OutFile $z;" ^
            "$t=Join-Path $env:TEMP 'jf_extract';" ^
            "if(Test-Path $t){Remove-Item $t -Recurse -Force};" ^
            "Expand-Archive -Path $z -DestinationPath $t -Force;" ^
            "$src=(Get-ChildItem $t -Directory | Select-Object -First 1).FullName;" ^
            "Copy-Item \"$src\*\" '%INSTALL_DIR%' -Recurse -Force"
        if !ERRORLEVEL! neq 0 (
            echo [X] Gagal mengunduh kode. Periksa koneksi internet.
            pause
            exit /b 1
        )
    )
)
echo [OK] Kode siap.

:: ── Setup venv + install ────────────────────────────────────────────────────
echo.
echo [*] Menyiapkan lingkungan ^& memasang dependensi...
cd /d "%INSTALL_DIR%"
if exist ".venv" rmdir /s /q ".venv" >nul 2>&1
%PY% -m venv .venv
if !ERRORLEVEL! neq 0 (
    echo [X] Gagal membuat lingkungan ^(venv^).
    pause
    exit /b 1
)
.venv\Scripts\pip install -q --upgrade pip >nul 2>&1
.venv\Scripts\pip install -q .
if !ERRORLEVEL! neq 0 (
    echo [X] Gagal memasang dependensi. Periksa koneksi internet lalu coba lagi.
    pause
    exit /b 1
)
echo [OK] Dependensi terpasang.

:: ── Daftarkan perintah `jf` ─────────────────────────────────────────────────
echo.
echo [*] Mendaftarkan perintah 'jf'...
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

> "%BIN_DIR%\jf.cmd" (
    echo @echo off
    echo setlocal
    echo set "INSTALL_DIR=%%USERPROFILE%%\.jf"
    echo if defined JF_INSTALL_DIR set "INSTALL_DIR=%%JF_INSTALL_DIR%%"
    echo.
    echo if exist "%%INSTALL_DIR%%\.git" ^(
    echo     cd /d "%%INSTALL_DIR%%"
    echo     for /f "tokens=*" %%%%i in ^('git status --porcelain'^) do set "DIRTY=%%%%i"
    echo     if not defined DIRTY ^(
    echo         for /f "tokens=*" %%%%i in ^('git rev-parse HEAD'^) do set "CURRENT=%%%%i"
    echo         git pull --quiet 2^>nul
    echo         for /f "tokens=*" %%%%i in ^('git rev-parse HEAD'^) do set "NEW=%%%%i"
    echo         if not "%%CURRENT%%"=="%%NEW%%" ^(
    echo             echo Update ditemukan! Memasang...
    echo             "%%INSTALL_DIR%%\.venv\Scripts\pip.exe" install -q . ^|^| echo Gagal update, lanjut versi lama.
    echo         ^)
    echo     ^)
    echo ^)
    echo.
    echo "%%INSTALL_DIR%%\.venv\Scripts\python.exe" -m jurnal_finder %%*
)
echo [OK] Perintah 'jf' siap.

:: ── Tambah BIN_DIR ke PATH user (tanpa menimpa PATH yang ada) ───────────────
set "USERPATH="
for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v PATH 2^>nul ^| findstr /i "PATH"') do set "USERPATH=%%b"
echo !USERPATH! | findstr /i /c:"%BIN_DIR%" >nul 2>&1
if errorlevel 1 (
    if defined USERPATH (
        setx PATH "!USERPATH!;%BIN_DIR%" >nul 2>&1
    ) else (
        setx PATH "%BIN_DIR%" >nul 2>&1
    )
    echo.
    echo [!] Buka jendela Command Prompt BARU agar perintah 'jf' bisa dipakai.
)

echo.
echo ================================================
echo   [OK] Instalasi selesai!
echo ================================================
echo.
echo   Cara pakai:
echo      jf                                   (mode dipandu, paling mudah)
echo      jf --topik "pengaruh inflasi"        (langsung dari terminal)
echo.
echo   Catatan: kalau 'jf' belum dikenali, tutup jendela ini,
echo   buka Command Prompt BARU, lalu coba lagi.
echo.
pause
exit /b 0

:: ═══════════════════════════════════════════════════════════════════════════
:find_python
for %%p in (python py) do (
    if "!PY!"=="" (
        %%p -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if !ERRORLEVEL! equ 0 set "PY=%%p"
    )
)
exit /b 0
