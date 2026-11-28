@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   CitroenC4Monitor - EXE build
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python 3 was not found.
        echo Install Python 3 and enable "Add Python to PATH".
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

echo [1/4] Checking Python...
%PYTHON% --version
if errorlevel 1 goto :error

echo.
echo [2/4] Installing application dependencies...
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo [3/4] Installing PyInstaller...
%PYTHON% -m pip install pyinstaller
if errorlevel 1 goto :error

echo.
echo [4/4] Building executable...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist CitroenC4Monitor.spec del /q CitroenC4Monitor.spec

%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name CitroenC4Monitor main.py
if errorlevel 1 goto :error

echo.
echo ==========================================
echo BUILD SUCCESSFUL
echo Executable: %~dp0dist\CitroenC4Monitor.exe
echo ==========================================
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Check the error messages above.
pause
exit /b 1
