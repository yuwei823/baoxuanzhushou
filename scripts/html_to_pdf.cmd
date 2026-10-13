@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Convert the presentation HTML to PDF with Chrome or Edge.
rem Usage: html_to_pdf.cmd [input.html] [output.pdf] [browser.exe]

for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"

if "%~1"=="" (
    set "INPUT=%PROJECT_ROOT%\src\insurance_audit\static\intro.html"
) else (
    for %%I in ("%~1") do set "INPUT=%%~fI"
)

if "%~2"=="" (
    set "OUTPUT=%PROJECT_ROOT%\output\pdf\insurance-marketing-audit-introduction.pdf"
) else (
    for %%I in ("%~2") do set "OUTPUT=%%~fI"
)

if not "%~3"=="" set "BROWSER=%~f3"
if not defined BROWSER if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "BROWSER=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if not exist "%INPUT%" (
    echo [ERROR] Input HTML not found: "%INPUT%"
    exit /b 1
)

if not defined BROWSER (
    echo [ERROR] Chrome or Edge was not found.
    echo         Pass the browser executable as the third argument.
    exit /b 2
)

if not exist "%BROWSER%" (
    echo [ERROR] Browser executable not found: "%BROWSER%"
    exit /b 2
)

for %%I in ("%OUTPUT%") do if not exist "%%~dpI" mkdir "%%~dpI"
set "TEMP_OUTPUT=%OUTPUT%.tmp.pdf"
set "PROFILE=%TEMP%\insurance-audit-pdf-%RANDOM%-%RANDOM%"
set "BROWSER_LOG=%TEMP%\insurance-audit-pdf-%RANDOM%-%RANDOM%.log"

if exist "%TEMP_OUTPUT%" del /q "%TEMP_OUTPUT%"
mkdir "%PROFILE%" >nul 2>nul

echo Rendering PDF...
"%BROWSER%" ^
    --headless=new ^
    --disable-gpu ^
    --hide-scrollbars ^
    --allow-file-access-from-files ^
    --run-all-compositor-stages-before-draw ^
    --print-to-pdf-no-header ^
    --user-data-dir="%PROFILE%" ^
    --print-to-pdf="%TEMP_OUTPUT%" ^
    "%INPUT%" >"%BROWSER_LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if exist "%PROFILE%" rmdir /s /q "%PROFILE%"

if not "%EXIT_CODE%"=="0" (
    if exist "%BROWSER_LOG%" type "%BROWSER_LOG%"
    if exist "%BROWSER_LOG%" del /q "%BROWSER_LOG%"
    if exist "%TEMP_OUTPUT%" del /q "%TEMP_OUTPUT%"
    echo [ERROR] Browser PDF export failed with exit code %EXIT_CODE%.
    exit /b %EXIT_CODE%
)

if exist "%BROWSER_LOG%" del /q "%BROWSER_LOG%"

if not exist "%TEMP_OUTPUT%" (
    echo [ERROR] The browser exited successfully but did not create a PDF.
    exit /b 3
)

for %%I in ("%TEMP_OUTPUT%") do if %%~zI LSS 1000 (
    del /q "%TEMP_OUTPUT%"
    echo [ERROR] The generated PDF is unexpectedly small.
    exit /b 4
)

move /y "%TEMP_OUTPUT%" "%OUTPUT%" >nul
if errorlevel 1 (
    echo [ERROR] Could not move the generated PDF to "%OUTPUT%".
    exit /b 5
)

echo Created: "%OUTPUT%"
exit /b 0
