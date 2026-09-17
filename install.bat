@echo off
setlocal

set "INSTALL_DIR=%USERPROFILE%\.jf"
set "REPO_URL=%~1"

echo Installing Jurnal Finder...

:: Setup directory
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

if defined REPO_URL (
    echo Cloning dari %REPO_URL%...
    git clone "%REPO_URL%" "%INSTALL_DIR%" 2>nul || (
        cd /d "%INSTALL_DIR%" && git pull
    )
) else (
    echo Copying...
    xcopy "%~dp0*" "%INSTALL_DIR%\" /E /Y /Q >nul
)

:: Setup venv + install
cd /d "%INSTALL_DIR%"
python -m venv .venv
.venv\Scripts\pip install -q .

:: Bikin wrapper command
set "BIN_DIR=%USERPROFILE%\.local\bin"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

(
    echo @echo off
    echo "%INSTALL_DIR%\.venv\Scripts\python.exe" -m jurnal_finder %%*
) > "%BIN_DIR%\jf.cmd"

:: Tambah PATH (via setx)
echo Menambah %BIN_DIR% ke PATH...
setx PATH "%BIN_DIR%;%PATH%" >nul 2>&1

echo.
echo Install selesai!
echo.
echo Cara pakai:
echo    jf --keyword-en "machine learning" -n 10
echo    jf
echo.
echo NOTE: Buka terminal baru atau restart VS Code agar PATH terupdate.
