@echo off
setlocal
chcp 65001 >nul

set "PYTHON=%~dp0python\python.exe"
if not exist "%PYTHON%" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo  ERROR: Python was not found.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

"%PYTHON%" "%~dp0installer.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
