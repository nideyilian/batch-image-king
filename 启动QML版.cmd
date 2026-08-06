@echo off
setlocal

cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0start_qml.py" %*
    goto :result
)

where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0start_qml.py" %*
    goto :result
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0start_qml.py" %*
    goto :result
)

echo Python 3 was not found.
echo Install Python and run: pip install -r requirements.txt
pause
exit /b 9009

:result
set "exit_code=%errorlevel%"
if not "%exit_code%"=="0" (
    echo.
    echo QML startup failed with exit code %exit_code%.
    echo Check the error message above, then press any key to close.
    pause
)
exit /b %exit_code%
