
@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  QUANTEXA - Full Stack Launcher
::  Services: Backend (FastAPI) | Frontend (Vite) | OpenClaw | Pipeline
:: ============================================================

title QUANTEXA Launcher

echo.
echo  ============================================================
echo    QUANTEXA Full Stack Launcher
echo  ============================================================
echo.

:: Root directory of the project
set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

set BACKEND_DIR=%ROOT%\backend
set FRONTEND_DIR=%ROOT%\frontend
set OPENCLAW_DIR=%ROOT%\openclaw
set PIPELINE_DIR=%ROOT%\financial-data-pipeline
set VENV_DIR=%ROOT%\venv

:: ---------- Activate Python venv ----------------------------
echo [STEP 1] Checking Python virtual environment...
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
    echo         Venv activated.
) else (
    echo         [WARN] No venv found. Using system Python.
)
echo.

:: ---------- BACKEND (FastAPI, port 8000) --------------------
echo [STEP 2] Launching Backend  ^>  http://127.0.0.1:8000
start "QUANTEXA Backend" cmd /k "title QUANTEXA BACKEND & color 0A & cd /d %BACKEND_DIR% & uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo         Green window opened.
echo.
timeout /t 3 /nobreak >nul

:: ---------- FRONTEND (Vite, port 3000) ----------------------
echo [STEP 3] Launching Frontend ^>  http://localhost:3000
start "QUANTEXA Frontend" cmd /k "title QUANTEXA FRONTEND & color 0B & cd /d %FRONTEND_DIR% & npm run dev"
echo         Cyan window opened.
echo.

:: ---------- OPENCLAW ----------------------------------------
echo [STEP 4] Launching OpenClaw gateway...
start "QUANTEXA OpenClaw" cmd /k "title QUANTEXA OPENCLAW & color 0D & cd /d %OPENCLAW_DIR% & node openclaw.mjs"
echo         Magenta window opened.
echo.

:: ---------- PIPELINE (optional) ----------------------------
echo ============================================================
set /p "RUN_PIPELINE=Run financial data pipeline now? (y/n): "
echo.
if /i "%RUN_PIPELINE%"=="y" (
    set /p "BATCH_ID=Enter batch_id (press ENTER for BATCH_DEFAULT): "
    if "!BATCH_ID!"=="" set BATCH_ID=BATCH_DEFAULT
    echo.
    echo  Launching Pipeline for batch_id=!BATCH_ID!
    start "QUANTEXA Pipeline" cmd /k "title QUANTEXA PIPELINE & color 0E & cd /d %PIPELINE_DIR% & python run_pipeline.py !BATCH_ID!"
    echo         Yellow window opened.
) else (
    echo  Pipeline skipped.
    echo  To run manually:
    echo    cd financial-data-pipeline
    echo    python run_pipeline.py
)

echo.
echo ============================================================
echo   All services launched!
echo.
echo   Backend API  ^>  http://127.0.0.1:8000
echo   Swagger Docs ^>  http://127.0.0.1:8000/docs
echo   Frontend     ^>  http://localhost:3000
echo   OpenClaw     ^>  see magenta terminal window
echo ============================================================
echo.
echo   (Close this window anytime - services keep running)
pause >nul
endlocal
