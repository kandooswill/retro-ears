@echo off
setlocal
rem Double-click to start retro-ears on Windows.
cd /d "%~dp0"
set "APP_DIR=%CD%"

set "UV=%APP_DIR%\bin\uv.exe"
if exist "%UV%" goto have_uv
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if defined UV goto have_uv
echo Download retro-ears from https://github.com/kandooswill/retro-ears/releases
call :wait_for_key
exit /b 1

:have_uv
set "UV_PYTHON_INSTALL_DIR=%APP_DIR%\.runtime\python"
set "UV_CACHE_DIR=%APP_DIR%\.runtime\cache"
set "UV_PROJECT_ENVIRONMENT=%APP_DIR%\.runtime\venv"
set "UV_PYTHON_PREFERENCE=only-managed"
set "RETRO_UV=%UV%"

set /p VERSION=<VERSION
set "INSTALLED="
if exist ".runtime\installed-version" set /p INSTALLED=<".runtime\installed-version"
if "%INSTALLED%"=="%VERSION%" goto run

echo Setting up retro-ears - the first run takes 1-2 minutes...
call "%UV%" sync --frozen --no-dev
if errorlevel 1 (
  echo Setup failed - check your internet connection and try again
  call :wait_for_key
  exit /b 1
)
if not exist ".runtime" mkdir ".runtime"
>".runtime\installed-version" <nul set /p "=%VERSION%"

:run
call "%UV%" run --no-sync python app.py %*
set "CODE=%ERRORLEVEL%"
if "%CODE%"=="42" (
  echo Restarting...
  goto run
)
echo retro-ears stopped. You can close this window.
call :wait_for_key
exit /b %CODE%

:wait_for_key
if defined RETRO_NO_PAUSE exit /b 0
pause
exit /b 0
