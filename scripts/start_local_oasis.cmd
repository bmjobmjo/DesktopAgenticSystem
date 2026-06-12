@echo off
setlocal

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"

set "PY_EXE=python"
if exist "%ROOT%\.venv\Scripts\python.exe" set "PY_EXE=%ROOT%\.venv\Scripts\python.exe"
if /I "%PY_EXE%"=="python" if exist "C:\Espressif\tools\idf-python\3.11.2\python.exe" set "PY_EXE=C:\Espressif\tools\idf-python\3.11.2\python.exe"
if /I "%PY_EXE%"=="python" if exist "C:\Users\Bijumon\AppData\Local\Programs\Python\Python313\python.exe" set "PY_EXE=C:\Users\Bijumon\AppData\Local\Programs\Python\Python313\python.exe"

set "NODE_EXE=node"
if exist "D:\programs\node\node.exe" set "NODE_EXE=D:\programs\node\node.exe"

echo Starting OASIS API on http://127.0.0.1:8788
start "OASIS API 8788" cmd.exe /k "cd /d %ROOT% && set DAS_API_PORT=8788 && \"%PY_EXE%\" api_start.py"

echo Starting OASIS UI on http://127.0.0.1:5199
start "OASIS UI 5199" cmd.exe /k "cd /d %ROOT%\apps\ui_web && \"%NODE_EXE%\" node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5199 --strictPort"

echo.
echo UI:    http://127.0.0.1:5199
echo API:   http://127.0.0.1:8788
echo Login: admin / admin123

endlocal
