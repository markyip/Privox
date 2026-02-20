@echo off
setlocal
title Privox Uninstaller

:: 1. Detect Installation Directory
set "TARGET_DIR=%~dp0"
:: Remove trailing backslash if present
if "%TARGET_DIR:~-1%"=="\" set "TARGET_DIR=%TARGET_DIR:~0,-1%"

:: 2. If running normally (not self-copied), initiate the cleanup process
if "%~1"=="__CLEANUP__" goto :CLEANUP

:: Check for quiet/silent flag
set "SILENT=0"
if /i "%~1"=="/S" set "SILENT=1"
if /i "%~1"=="/quiet" set "SILENT=1"

if "%SILENT%"=="1" goto :CONFIRMED

echo ==========================================
echo           PRIVOX UNINSTALLER
echo ==========================================
echo.
echo This script will:
echo  1. Stop Privox if running.
echo  2. Remove Startup Registry Keys.
echo  3. Delete the installation folder: "%TARGET_DIR%"
echo.
set /p CONFIRM=Type 'Y' to confirm uninstallation: 
if /i not "%CONFIRM%"=="Y" exit

:CONFIRMED
echo.
echo Preparing cleanup...

:: Copy self to TEMP to run independently (so we can delete this folder)
copy /y "%~f0" "%TEMP%\uninstall_privox_temp.bat" >nul
:: Launch the temp copy, passing the INSTALL_DIR as an argument
start "" /min "%TEMP%\uninstall_privox_temp.bat" __CLEANUP__ "%TARGET_DIR%"
exit

:CLEANUP
:: Wait a moment for the original batch file to close
timeout /t 2 /nobreak >nul

set "INSTALL_DIR=%~2"

:: 3. Kill Privox Processes
echo Stopping Privox...
taskkill /F /IM Privox.exe >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Privox*" >nul 2>&1

:: 4. Remove Registry Keys
echo Removing Registry Keys...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Privox" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Privox" /f >nul 2>&1

:: 5. Remove Shortcut (if exists)
if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Privox.lnk" (
    del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Privox.lnk" >nul 2>&1
)

:: 6. Delete Installation Directory
echo Deleting Files...
if exist "%INSTALL_DIR%" (
    rd /s /q "%INSTALL_DIR%"
)

:: 7. Self-Destruct this temp script
(goto) 2>nul & del "%~f0"
