@echo off
setlocal enabledelayedexpansion

set "INSTALL_DIR=%USERPROFILE%\.jf"
set "REPO_URL=%~1"

echo Installing Jurnal Finder...

where python >nul 2>&1 || (
    echo [ERROR] Python tidak ditemukan di PATH. Install Python 3.10+ dulu.
    exit /b 1
)

:: Setup directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: ── Ambil source code ──────────────────────────────────────────────────────
if defined REPO_URL (
    echo Cloning dari %REPO_URL%...
    if exist "%INSTALL_DIR%\.git" (
        git -C "%INSTALL_DIR%" pull --quiet
    ) else (
        git clone "%REPO_URL%" "%INSTALL_DIR%"
    )
) else (
    if /i "%~dp0"=="%INSTALL_DIR%\" (
        echo Script sudah berada di %INSTALL_DIR% -- lewati copy.
    ) else (
        echo Copying...
        where robocopy >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            robocopy "%~dp0." "%INSTALL_DIR%" /E ^
                /XD .git .venv venv build dist .opencode node_modules __pycache__ .mypy_cache .pytest_cache *.egg-info ^
                /XF *.pyc /NFL /NDL /NJH /NJS /NP >nul
            if !ERRORLEVEL! GEQ 8 (
                echo [ERROR] Copy gagal.
                exit /b 1
            )
        ) else (
            :: Fallback: xcopy dengan exclude list (.git/.venv/build tidak ikut)
            > "%TEMP%\jf_exclude.txt" (
                echo .venv\
                echo \venv\
                echo \build\
                echo \dist\
                echo \.git\
                echo \.opencode\
                echo \node_modules\
                echo \__pycache__\
                echo .egg-info\
            )
            xcopy "%~dp0*" "%INSTALL_DIR%\" /E /I /H /Y /Q /EXCLUDE:"%TEMP%\jf_exclude.txt" >nul
        )
    )
)

:: Setup venv + install
cd /d "%INSTALL_DIR%"
python -m venv .venv
.venv\Scripts\pip install -q --upgrade pip
.venv\Scripts\pip install -q .

:: Bikin wrapper command dengan auto-update
set "BIN_DIR=%USERPROFILE%\.local\bin"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

> "%BIN_DIR%\jf.cmd" (
    echo @echo off
    echo setlocal
    echo set "INSTALL_DIR=%%USERPROFILE%%\.jf"
    echo.
    echo :: Auto-update (hanya jika tree bersih^)
    echo if exist "%%INSTALL_DIR%%\.git" ^(
    echo     cd /d "%%INSTALL_DIR%%"
    echo     for /f "tokens=*" %%%%i in ^('git status --porcelain'^) do set "DIRTY=%%%%i"
    echo     if not defined DIRTY ^(
    echo         for /f "tokens=*" %%%%i in ^('git rev-parse HEAD'^) do set "CURRENT=%%%%i"
    echo         git pull --quiet 2^>nul
    echo         for /f "tokens=*" %%%%i in ^('git rev-parse HEAD'^) do set "NEW=%%%%i"
    echo         if not "%%CURRENT%%"=="%%NEW%%" ^(
    echo             echo Update ditemukan! Installing...
    echo             "%%INSTALL_DIR%%\.venv\Scripts\pip.exe" install -q . ^|^| echo Gagal update, lanjut versi lama.
    echo         ^)
    echo     ^)
    echo ^)
    echo.
    echo "%%INSTALL_DIR%%\.venv\Scripts\python.exe" -m jurnal_finder %%*
)

:: Tambah BIN_DIR ke PATH user (tanpa menimpa/merusak PATH)
set "USERPATH="
for /f "tokens=2,*" %%a in ('reg query HKCU\Environment /v PATH 2^>nul ^| findstr /i "PATH"') do set "USERPATH=%%b"
echo !USERPATH! | findstr /i /c:"%BIN_DIR%" >nul 2>&1
if errorlevel 1 (
    if defined USERPATH (
        setx PATH "!USERPATH!;%BIN_DIR%" >nul 2>&1
    ) else (
        setx PATH "%BIN_DIR%" >nul 2>&1
    )
    echo Menambah %BIN_DIR% ke PATH...
)

echo.
echo Install selesai!
echo.
echo Cara pakai:
echo    jf --keyword-en "machine learning" -n 10
echo    jf
echo.
echo NOTE: Auto-update: jf akan otomatis update setiap kali dijalankan