@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   CyberOps Knowledge Base - Startup Script
echo ============================================
echo.

:: ------------------------------------------------
:: Configuration
:: ------------------------------------------------
set DEFAULT_BACKEND_PORT=17000
set DEFAULT_FRONTEND_PORT=17001
set BACKEND_PORT=%DEFAULT_BACKEND_PORT%
set FRONTEND_PORT=%DEFAULT_FRONTEND_PORT%
set SCRIPT_DIR=%~dp0

:: ------------------------------------------------
:: Prerequisite checks
:: ------------------------------------------------
echo [*] Checking prerequisites...

where python >nul 2>&1
if !errorlevel! neq 0 (
    where py >nul 2>&1
    if !errorlevel! neq 0 (
        echo [ERROR] Python is not installed or not in PATH.
        echo         Please install Python 3.10+ from https://www.python.org/downloads/
        goto :error_exit
    )
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)
echo [OK] Python found: !PYTHON_CMD!

where node >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo         Please install Node.js 18+ from https://nodejs.org/
    goto :error_exit
)
echo [OK] Node.js found

where npm >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] npm is not installed or not in PATH.
    goto :error_exit
)
echo [OK] npm found
echo.

:: ------------------------------------------------
:: Check backend port availability
:: ------------------------------------------------
echo [*] Checking if port !BACKEND_PORT! is available for backend...
netstat -ano | findstr ":!BACKEND_PORT! " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [!] Port !BACKEND_PORT! is already in use. Searching for an available port...
    for /L %%p in (17002,1,17100) do (
        netstat -ano | findstr ":%%p " | findstr "LISTENING" >nul 2>&1
        if !errorlevel! neq 0 (
            set BACKEND_PORT=%%p
            goto :found_backend
        )
    )
    echo [ERROR] Could not find an available port for the backend ^(tried 17002-17100^).
    goto :error_exit
)
:found_backend
echo [OK] Backend will use port !BACKEND_PORT!
echo.

:: ------------------------------------------------
:: Check frontend port availability
:: ------------------------------------------------
echo [*] Checking if port !FRONTEND_PORT! is available for frontend...
netstat -ano | findstr ":!FRONTEND_PORT! " | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [!] Port !FRONTEND_PORT! is already in use. Searching for an available port...
    for /L %%p in (17101,1,17200) do (
        netstat -ano | findstr ":%%p " | findstr "LISTENING" >nul 2>&1
        if !errorlevel! neq 0 (
            set FRONTEND_PORT=%%p
            goto :found_frontend
        )
    )
    echo [ERROR] Could not find an available port for the frontend ^(tried 17101-17200^).
    goto :error_exit
)
:found_frontend
echo [OK] Frontend will use port !FRONTEND_PORT!
echo.

:: ------------------------------------------------
:: Setup Python virtual environment
:: ------------------------------------------------
echo [*] Checking Python virtual environment...
if exist "!SCRIPT_DIR!backend\venv\Scripts\activate.bat" (
    echo [OK] Virtual environment found.
) else (
    echo [!] Virtual environment not found. Creating one...
    !PYTHON_CMD! -m venv "!SCRIPT_DIR!backend\venv"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        goto :error_exit
    )
    echo [OK] Virtual environment created.
    echo [*] Installing backend dependencies...
    call "!SCRIPT_DIR!backend\venv\Scripts\activate.bat"
    pip install -r "!SCRIPT_DIR!backend\requirements.txt"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install backend dependencies.
        goto :error_exit
    )
    echo [OK] Backend dependencies installed.
)
echo.

:: ------------------------------------------------
:: Setup frontend dependencies
:: ------------------------------------------------
echo [*] Checking frontend dependencies...
if exist "!SCRIPT_DIR!frontend\node_modules" (
    echo [OK] Node modules found.
) else (
    echo [!] Node modules not found. Installing...
    pushd "!SCRIPT_DIR!frontend"
    npm install
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install frontend dependencies.
        popd
        goto :error_exit
    )
    popd
    echo [OK] Frontend dependencies installed.
)
echo.

:: ------------------------------------------------
:: Set environment variables for child processes
:: ------------------------------------------------
set PORT=!FRONTEND_PORT!
set BACKEND_PORT=!BACKEND_PORT!

:: ------------------------------------------------
:: Start Backend
:: ------------------------------------------------
echo [*] Starting backend on port !BACKEND_PORT!...
start "CyberOps Backend [port !BACKEND_PORT!]" cmd /k "cd /d "!SCRIPT_DIR!backend" && call venv\Scripts\activate.bat && uvicorn app.main:app --reload --port !BACKEND_PORT!"

:: Give backend a moment to initialize
timeout /t 3 /nobreak >nul

:: ------------------------------------------------
:: Start Frontend
:: ------------------------------------------------
echo [*] Starting frontend on port !FRONTEND_PORT!...
start "CyberOps Frontend [port !FRONTEND_PORT!]" cmd /k "cd /d "!SCRIPT_DIR!frontend" && set PORT=!FRONTEND_PORT! && set BACKEND_PORT=!BACKEND_PORT! && npm run dev"

:: ------------------------------------------------
:: Summary
:: ------------------------------------------------
echo.
echo ============================================
echo   CyberOps is starting up!
echo ============================================
echo.
if !BACKEND_PORT! neq %DEFAULT_BACKEND_PORT% (
    echo   [NOTE] Backend port changed: %DEFAULT_BACKEND_PORT% -^> !BACKEND_PORT!
)
if !FRONTEND_PORT! neq %DEFAULT_FRONTEND_PORT% (
    echo   [NOTE] Frontend port changed: %DEFAULT_FRONTEND_PORT% -^> !FRONTEND_PORT!
)
echo.
echo   Frontend: http://localhost:!FRONTEND_PORT!
echo   Backend:  http://localhost:!BACKEND_PORT!
echo   API Docs: http://localhost:!BACKEND_PORT!/docs
echo.
echo   Two new terminal windows have been opened.
echo   Close them or press Ctrl+C in each to stop the servers.
echo ============================================
echo.
pause
exit /b 0

:error_exit
echo.
echo [FAILED] Startup aborted due to errors.
pause
exit /b 1
