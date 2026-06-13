@echo off
chcp 65001 > nul
echo ============
echo    KnowledgeForge / 知炬 — 启动服务
echo ============
echo.

REM --- 1. 启动 Qdrant ---
echo [1/3] 启动 Qdrant 向量数据库...
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    start "Qdrant" /MIN D:\qdrant\qdrant.exe --config-path D:/qdrant/config/config.yaml
    echo   Qdrant 已启动 (端口 6333)
    timeout /t 3 /nobreak >nul
) else (
    echo   Qdrant 已在运行
)

REM --- 2. 确认 Ollama ---
echo [2/3] 确认 Ollama 嵌入服务...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I "ollama.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    echo   [!] Ollama 未运行，请手动启动 Ollama
) else (
    echo   Ollama 已在运行 (端口 11434)
)

echo [3/3] 选择启动模式：
echo   1. 命令行模式（kb_query.py）
echo   2. Web UI 模式（Streamlit）
echo.
set /p mode="请选择 (1/2): "

if "%mode%"=="1" (
    echo.
    echo ============
    echo   服务已就绪! 使用 kb_query.py 进行检索:
    echo     python kb_query.py "你的问题"
    echo     python kb_query.py --ingest 文档路径
    echo ============
    pause
) else if "%mode%"=="2" (
    echo.
    echo   正在启动 Web UI...
    echo   浏览器将自动打开 http://localhost:8501
    echo.
    timeout /t 2 /nobreak >nul
    start http://localhost:8501
    "C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe" -m streamlit run app.py --server.port 8501 --server.headless false
) else (
    echo.
    echo   无效选择，退出。
    pause
)
