@echo off
setlocal enabledelayedexpansion

:: ===== Prompt User for Input =====
set /p UBUNTU_USER=Enter Ubuntu username: 
set /p UBUNTU_IP=Enter Ubuntu IP address: 

:: ===== USER CONFIGURATION =====
set "REMOTE_FILE_DIR=/nas/storage/files"
set "LOCAL_PORT=9090"
set "REMOTE_PORT=8888"
:: ==============================

:: ===== Start the HTTP server remotely over SSH =====
echo.
echo Starting HTTP server on Ubuntu...
ssh %UBUNTU_USER%@%UBUNTU_IP% "nohup python3 %REMOTE_FILE_DIR%/server.py > /dev/null 2>&1 &"

:: ===== Wait briefly to allow HTTP server to start =====
timeout /t 2 > nul

:: ===== Start SSH tunnel =====
echo.
echo Creating SSH tunnel (localhost:%LOCAL_PORT% : %UBUNTU_IP%:%REMOTE_PORT%)...
start "" cmd /k ssh -L %LOCAL_PORT%:localhost:%REMOTE_PORT% %UBUNTU_USER%@%UBUNTU_IP%

:: ===== Display NAS URL for user to use =====
set "STORAGE_URL=http://localhost:%LOCAL_PORT%"
echo.
echo ==================================================
echo You can now access the storage at:
echo     !STORAGE_URL!
echo.
echo Open it in any browser.
echo The SSH tunnel is running in a separate window.
echo ==================================================
pause
