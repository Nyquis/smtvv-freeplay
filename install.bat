@echo off
REM SPDX-FileCopyrightText: 2026 Nyquis
REM SPDX-FileCopyrightText: 2026 the countlessbats/smtvv-freeplay authors
REM SPDX-License-Identifier: MIT AND Apache-2.0
REM Modified by Nyquis from the upstream MIT project; see LICENSING.md.
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
