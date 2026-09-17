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

:: Bikin wrapper command dengan auto-update
set "BIN_DIR=%USERPROFILE%\.local\bin"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

> "%BIN_DIR%\jf.cmd" (
    echo @echo off
    echo setlocal
    echo set "INSTALL_DIR=%%USERPROFILE%%\.jf"
    echo.
    echo :: Auto-update
    echo if exist "%%INSTALL_DIR%%\.git" ^(
    echo     cd /d "%%INSTALL_DIR%%"
    echo     for /f "tokens=*" %%%%i in ^('git rev-parse HEAD'^) do set "CURRENT=%%%%i"
    echo     git pull --quiet 2^>nul
    echo     for /f "tokens=*" %%%%i in ^('git rev-parse HEAD'^) do set "NEW=%%%%i"
    echo     if not "%%CURRENT%%"=="%%NEW%%" ^(
    echo         echo Update ditemukan! Installing...
    echo         "%%INSTALL_DIR%%\.venv\Scripts\pip.exe" install -q .
    echo     ^)
    echo ^)
    echo.
    echo "%%INSTALL_DIR%%\.venv\Scripts\python.exe" -m jurnal_finder %%*
)

:: Tambah PATH
echo Menambah %BIN_DIR% ke PATH...
setx PATH "%BIN_DIR%;%PATH%" >nul 2>&1

echo.
echo Install selesai!
echo.
echo Cara pakai:
echo    jf --keyword-en "machine learning" -n 10
echo    jf
echo.
echo NOTE: Auto-update: jf akan otomatis update setiap kali dijalankan
