@echo off
setlocal

call :kill_port 5199
call :kill_port 8788

echo Done.
endlocal
exit /b 0

:kill_port
set "PORT=%~1"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
  echo Stopping PID %%P on port %PORT%
  taskkill /PID %%P /F >nul 2>nul
)
exit /b 0
