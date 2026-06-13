@echo off
chcp 65001 > nul
echo ================================
echo    KnowledgeForge / 知炬 — Web UI
echo ================================
echo.

REM 检查 streamlit 是否安装
"C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe" -c "import streamlit" 2>nul
if errorlevel 1 (
    echo [错误] streamlit 未安装，正在安装...
    "C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe" -m pip install streamlit requests -q
)

echo [1/3] 检查 Qdrant 服务...
tasklist | find "qdrant" > nul
if errorlevel 1 (
    echo   Qdrant 未运行，正在启动...
    start /min cmd /k "cd /d/private-gpt && .\start.bat"
    timeout /t 5 > nul
) else (
    echo   Qdrant 已运行
)

echo [2/3] 启动 Web UI...
echo   浏览器将自动打开 http://localhost:8501
echo.

REM 启动 streamlit
"C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe" -m streamlit run app.py --server.port 8501 --server.headless false

pause
