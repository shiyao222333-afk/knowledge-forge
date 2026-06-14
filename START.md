# 🚀 启动 KnowledgeForge

快速启动 Web UI 界面。

## 📋 前置要求

1. **Python 3.8+** 已安装
2. **Qdrant** 向量数据库已安装并运行（端口 6333）
3. **Ollama** 嵌入服务已安装并运行（端口 11434）（可选，用于OCR）

## 🪟 Windows 用户

### 方法一：一键启动（推荐）

双击运行 `run_ui.bat`，脚本会自动：
1. 检查 Python 和依赖
2. 安装缺少的依赖（streamlit、requests）
3. 检查端口是否被占用
4. 启动 Qdrant（如果未运行）
5. 启动 Web UI
6. 自动打开浏览器

### 方法二：手动启动

```bash
# 1. 安装依赖
pip install streamlit requests

# 2. 启动 Qdrant（如果未运行）
# 参考 Qdrant 官方文档

# 3. 启动 Web UI
python app.py
# 或者
streamlit run app.py --server.port 8501
```

## 🍎 macOS / 🐧 Linux 用户

### 方法一：一键启动（推荐）

```bash
# 1. 添加执行权限
chmod +x run_ui.sh

# 2. 运行脚本
./run_ui.sh
```

脚本会自动：
1. 检查 Python 和依赖
2. 安装缺少的依赖
3. 检查端口是否被占用
4. 启动 Qdrant（如果已安装）
5. 启动 Web UI
6. 自动打开浏览器

### 方法二：手动启动

```bash
# 1. 安装依赖
pip3 install streamlit requests

# 2. 启动 Qdrant（如果未运行）
# macOS: brew services start qdrant
# Linux: systemctl start qdrant

# 3. 启动 Web UI
python3 app.py
# 或者
streamlit run app.py --server.port 8501
```

## 🌐 访问地址

启动成功后，访问：
- **本地地址**: http://localhost:8501
- **网络地址**: http://你的IP地址:8501

## ⚠️ 常见问题

### 1. 端口 8501 被占用

**Windows**:
```bash
# 查看占用端口的进程
netstat -ano | find ":8501"

# 关闭进程
taskkill /PID <进程ID> /F
```

**macOS/Linux**:
```bash
# 查看占用端口的进程
lsof -i :8501

# 关闭进程
kill -9 <进程ID>
```

**或者修改端口**：
编辑 `run_ui.bat` 或 `run_ui.sh`，将 `PORT=8501` 改为其他端口（如 8502）

### 2. 浏览器没有自动打开

手动打开浏览器，访问 http://localhost:8501

### 3. 提示"Qdrant 未找到"

请参考 [README.md](README.md) 中的"快速开始"部分，安装并启动 Qdrant。

### 4. 提示"Ollama 未运行"

OCR 功能需要 Ollama，如果不需要 OCR，可以忽略此提示。

如果需要 OCR，请：
1. 安装 Ollama: https://ollama.com/
2. 启动 Ollama
3. 下载嵌入模型: `ollama pull nomic-embed-text`

### 5. 依赖安装失败

**Windows**:
```bash
# 使用国内镜像
pip install streamlit requests -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**macOS/Linux**:
```bash
# 使用国内镜像
pip3 install streamlit requests -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 6. 提示"Python 未找到"

请修改脚本中的 `PYTHON_EXE` 变量，设置为你的 Python 路径。

**Windows**:
```batch
# 查看 Python 路径
where python

# 修改为实际路径
set PYTHON_EXE=C:\path\to\your\python.exe
```

**macOS/Linux**:
```bash
# 查看 Python 路径
which python3

# 修改为实际路径
PYTHON_EXE=/path/to/your/python3
```

## 📝 高级配置

### 修改端口

编辑 `run_ui.bat`（Windows）或 `run_ui.sh`（macOS/Linux），修改以下行：
```bash
PORT=8501  # 改为其他端口
```

### 修改 Python 路径

编辑 `run_ui.bat`（Windows），修改以下行：
```batch
set PYTHON_EXE=C:\path\to\your\python.exe
```

### 禁用浏览器自动打开

编辑 `run_ui.bat`，注释掉以下行：
```batch
start "" cmd /c "timeout /t 2 > nul && start http://localhost:%PORT%"
```

编辑 `run_ui.sh`，注释掉以下行：
```bash
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:$PORT
elif command -v open &> /dev/null; then
    open http://localhost:$PORT
fi
```

## 🆘 需要帮助？

如果遇到问题，请：
1. 查看脚本输出的错误信息
2. 检查 [README.md](README.md) 中的"常见问题"
3. 在 GitHub 提交 Issue

---

**祝使用愉快！** 🎉
