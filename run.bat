@echo off
REM Athanor 启动脚本 — 自动杀掉旧进程再启动
chcp 65001 >nul

set PROJECT_DIR=%~dp0
set PYTHON=C:\Python314\python.exe
set PID_FILE=%PROJECT_DIR%.athanor.pid

echo ========================================
echo   Athanor · 熔知 启动脚本
echo ========================================

REM 1. 通过 PID 文件杀掉旧进程
if exist "%PID_FILE%" (
    set /p OLD_PID=<"%PID_FILE%"
    echo [1/4] 杀掉旧进程 (PID: %OLD_PID%) ...
    taskkill /F /PID %OLD_PID% >nul 2>&1
    del /q "%PID_FILE%" >nul 2>&1
    timeout /t 1 >nul
) else (
    echo [1/4] 无 PID 文件，跳过 ...
)

REM 2. 杀掉占用 8080 端口的进程
echo [2/4] 检查端口 8080 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080 " ^| findstr "LISTENING"') do (
    echo       杀掉占用端口的进程 (PID: %%a) ...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 >nul

REM 3. 杀掉所有运行 main.py 的 python 进程
echo [3/4] 清理残留的 python main.py 进程 ...
for /f "tokens=2" %%a in ('tasklist ^| findstr "python.exe"') do (
    wmic process where "ProcessId=%%a" get CommandLine 2>nul | findstr /i "main.py" >nul 2>&1
    if not errorlevel 1 (
        echo       杀掉 PID: %%a
        taskkill /F /PID %%a >nul 2>&1
    )
)
timeout /t 1 >nul

REM 4. 启动服务
echo [4/4] 启动 Athanor ...
echo       工作目录: %PROJECT_DIR%
echo       访问地址: <ADDRESS_REDACTED>
echo ========================================
echo.

cd /d "%PROJECT_DIR%"
start "Athanor" "%PYTHON%" main.py
