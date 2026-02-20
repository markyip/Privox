@echo off
setlocal
:: Privox Silent Uninstaller
:: This script handles the automated removal of Privox triggered by Windows Settings.

:: Standardize Path: Get current directory WITHOUT trailing backslash
set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

:: 1. If running as CLEANUP (from TEMP), perform the wipe
if "%~1"=="__CLEANUP__" goto :CLEANUP

:: 2. Migration to TEMP
:: Since we can't delete the folder while this script is running from it,
:: we copy ourselves to TEMP and launch from there.
set "TEMP_SCRIPT=%TEMP%\uninstall_privox_%RANDOM%.bat"
copy /y "%~f0" "%TEMP_SCRIPT%" >nul

:: Launch the second stage HIDDEN via PowerShell
:: This ensures the cleanup happens silently in the background.
powershell -WindowStyle Hidden -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%TEMP_SCRIPT%\" __CLEANUP__ \"%BASE_DIR%\"\"' -WindowStyle Hidden"
exit /b

:CLEANUP
set "TARGET_DIR=%~2"

:: Wait a bit for the original launcher to exit
timeout /t 2 /nobreak >nul

:: 3. Kill Processes (Force + Tree)
:: Kill by explicit title (Set in voice_input.py)
taskkill /F /T /FI "WINDOWTITLE eq Privox*" >nul 2>&1
:: Kill by possible image names (Dev and Frozen)
taskkill /F /T /IM Privox.exe >nul 2>&1
taskkill /F /T /IM python.exe /FI "WINDOWTITLE eq Privox*" >nul 2>&1
:: Fallback: PowerShell regex kill for any process spanning 'Privox' in title/arguments
powershell -Command "Get-Process | Where-Object { $_.MainWindowTitle -like '*Privox*' -or $_.ProcessName -eq 'Privox' } | Stop-Process -Force" >nul 2>&1

:: 4. Remove Registry Keys
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Privox" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Privox" /f >nul 2>&1

:: 5. Remove Shortcuts
set "START_MENU_AUTO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%START_MENU_AUTO%\Privox.lnk" del /f /q "%START_MENU_AUTO%\Privox.lnk" >nul 2>&1

set "START_MENU_PROG=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if exist "%START_MENU_PROG%\Privox.lnk" del /f /q "%START_MENU_PROG%\Privox.lnk" >nul 2>&1

:: 6. Wipe App Directory (with retry loop)
set "RETRY=0"
:RETRY_LOOP
if exist "%TARGET_DIR%" (
    rd /s /q "%TARGET_DIR%" >nul 2>&1
    if exist "%TARGET_DIR%" (
        set /a RETRY+=1
        if %RETRY% LSS 10 (
            timeout /t 2 /nobreak >nul
            goto :RETRY_LOOP
        )
    )
)

:: 7. Vanish (Self-delete the temp script)
(goto) 2>nul & del "%~f0"
