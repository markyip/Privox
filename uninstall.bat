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
set "EXE_CMD=powershell.exe -WindowStyle Hidden -Command \"& '%TEMP_SCRIPT%' __CLEANUP__ '%BASE_DIR%'\""
start "" %EXE_CMD%
exit /b

:CLEANUP
set "TARGET_DIR=%~2"

:: Wait a bit for the original launcher to exit
timeout /t 2 /nobreak >nul

:: 3. Kill Processes (Two-Stage: Graceful then Forced)
:: Stage 1: Try to close gracefully
taskkill /FI "WINDOWTITLE eq Privox_Settings_GUI" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Privox_Service_Background_Engine" >nul 2>&1
timeout /t 1 /nobreak >nul

:: Stage 2: Force-kill any lingering processes
:: We use exact window titles and command-line matching to avoid killing the IDE/Terminal
taskkill /F /T /FI "WINDOWTITLE eq Privox_Settings_GUI" >nul 2>&1
taskkill /F /T /FI "WINDOWTITLE eq Privox_Service_Background_Engine" >nul 2>&1
taskkill /F /T /IM Privox.exe >nul 2>&1

:: Fallback: PowerShell commandline match for python windowless processes (Robust & Safe)
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' OR Name = 'pythonw.exe'\" | Where-Object { $_.CommandLine -match 'voice_input\.py' -or $_.CommandLine -match 'gui_settings\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

:: Tray Refresh (Robust V2): Refreshes main tray AND overflow area by simulating mouse move
powershell -Command "$c='using System;using System.Runtime.InteropServices;public class T{[DllImport(\"user32.dll\")]public static extern IntPtr FindWindow(string l,string n);[DllImport(\"user32.dll\")]public static extern IntPtr FindWindowEx(IntPtr p,IntPtr c,string s,string w);[DllImport(\"user32.dll\")]public static extern int GetWindowRect(IntPtr h,out R r);[DllImport(\"user32.dll\")]public static extern int SendMessage(IntPtr h,int m,int w,int l);[StructLayout(LayoutKind.Sequential)]public struct R{public int L,T,Ri,B;}}';Add-Type -TypeDefinition $c;foreach($w in @('Shell_TrayWnd','NotifyIconOverflowWindow')){$h=[T]::FindWindow($w,$null);if($h -ne [IntPtr]::Zero){$t=[T]::FindWindowEx($h,[IntPtr]::Zero,'TrayNotifyWnd',$null);if($t -eq [IntPtr]::Zero){$t=$h};$p=[T]::FindWindowEx($t,[IntPtr]::Zero,'SysPager',$null);$tb=if($p -ne [IntPtr]::Zero){[T]::FindWindowEx($p,[IntPtr]::Zero,'ToolbarWindow32',$null)}else{[T]::FindWindowEx($t,[IntPtr]::Zero,'ToolbarWindow32',$null)};if($tb -ne [IntPtr]::Zero){$r=New-Object T+R;[T]::GetWindowRect($tb,[ref]$r);for($x=0;$x -lt ($r.Ri-$r.L);$x+=5){for($y=0;$y -lt ($r.B-$r.T);$y+=5){[T]::SendMessage($tb,0x0200,0,$x+($y*0x10000))}}}}}" >nul 2>&1

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
del /f /q "%TEMP%\uninstall_privox_*.vbs" >nul 2>&1
(goto) 2>nul & del "%~f0"
