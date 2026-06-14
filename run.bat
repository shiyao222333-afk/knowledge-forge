@echo off
REM ============================================================
REM  KnowledgeForge / ZhiJu - One-Click Launcher
REM  Auto-start Qdrant + Streamlit Web UI
REM ============================================================

set "PROJECT_DIR=D:\knowledge-forge"
set "PYTHON_EXE=C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe"
set "PORT=8501"

REM --- Runtime dependencies (paths on this machine) ---
set "KB_NODE_BIN=C:\Users\Lenovo\.workbuddy\binaries\node\versions\22.22.2\node.exe"
set "KB_NPM_ROOT=C:\Users\Lenovo\.workbuddy\binaries\node\workspace\node_modules"
set "KB_TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe"
set "KB_TESSDATA_PREFIX=D:\Tesseract-OCR\tessdata"

echo.
echo ==========================================
echo   KnowledgeForge / ZhiJu
echo ==========================================
echo.

REM --- Step 1: Go to project directory ---
echo [1/4] Project directory...
cd /d "%PROJECT_DIR%"
if errorlevel 1 (
    echo   [ERROR] Cannot find: %PROJECT_DIR%
    pause
    exit /b 1
)
echo   OK: %CD%

REM --- Step 2: Check Python ---
echo.
echo [2/4] Python...
if not exist "%PYTHON_EXE%" (
    echo   [ERROR] Python not found: %PYTHON_EXE%
    pause
    exit /b 1
)
echo   OK

REM --- Step 3: Auto-start Qdrant if not running ---
echo.
echo [3/4] Qdrant...
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    if exist "D:\qdrant\qdrant.exe" (
        start "Qdrant" /MIN D:\qdrant\qdrant.exe --config-path D:/qdrant/config/config.yaml
        echo   Qdrant started (port 6333)
        timeout /t 3 /nobreak > nul
    ) else (
        echo   [!] Qdrant not found at D:\qdrant\ - some features unavailable
    )
) else (
    echo   Qdrant already running
)

REM --- Step 4: Start Streamlit ---
echo.
echo [4/4] Starting Web UI...
echo.
echo   URL: http://localhost:%PORT%
echo   Press Ctrl+C to stop.
echo.

"%PYTHON_EXE%" -m streamlit run app.py --server.port %PORT% --server.headless=true --browser.gatherUsageStats=false

echo.
echo   Web UI stopped.
pause
