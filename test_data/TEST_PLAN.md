# KnowledgeForge 测试计划

> 项目: KnowledgeForge / 知炬 — 中文技术文档知识库问答系统  
> 日期: 2026-06-14  
> 测试环境: Windows, Python 3.13.12, Qdrant 1.18.2, Ollama (qwen3-embedding:4b)

---

## 前置条件检查

| # | 条件 | 验证方式 |
|---|------|---------|
| 1 | Qdrant 运行在 localhost:6333 | `curl http://localhost:6333/` |
| 2 | Ollama 运行在 localhost:11434 | `curl http://localhost:11434/api/tags` |
| 3 | qwen3-embedding:4b 已拉取 | 检查 Ollama 模型列表 |
| 4 | LLM API Key 已配置（问答测试需要） | `.env` 文件中 `KB_LLM_API_KEY` |
| 5 | Python 3.13.12 可用 | `python --version` |

---

## 测试阶段

### Phase 1 — 冒烟测试 (Smoke)

**目标**: 验证基础环境、语法和模块加载。

| # | 测试项 | 命令 / 方法 | 预期结果 |
|---|--------|------------|---------|
| 1.1 | 语法编译 | `python -m py_compile *.py` | 全部通过 |
| 1.2 | Qdrant 连接 | HTTP GET `localhost:6333/` | 200, 返回版本信息 |
| 1.3 | Ollama 连接 | HTTP GET `localhost:11434/api/tags` | 200, 含 qwen3-embedding:4b |
| 1.4 | 模块导入 | `import kb_query; from config.classifications import CLASSIFICATION_SCHEMES` | 成功导入 |
| 1.5 | 环境变量 | 检查 `KB_TESSERACT_PATH` 等 | 路径存在或使用默认 |

**运行**: `python test_runner.py --phase 1`

---

### Phase 2 — 功能测试 (Functional)

**目标**: 验证核心功能链路正常工作。

| # | 测试项 | 输入 | 预期 |
|---|--------|------|------|
| 2.1 | CLI 帮助 | `python kb_query.py --help` | 输出版本和用法 |
| 2.2 | 摄入 TXT | `--ingest 齿轮设计基础.txt --source 机械-手册` | 分块→embedding→Qdrant |
| 2.3 | 摄入纯文本 | `--text "内容" --source 测试` | 成功摄入 |
| 2.4 | 向量搜索 | `"齿轮失效" --top 3` | 返回 ≥1 条结果 |
| 2.5 | 去重检测 | 重复摄入同一文件 | 检测到重复并跳过 |
| 2.6 | 端到端问答 | `"齿轮的失效形式有哪些" --answer` | 返回 synthesis + HTML 路径 |
| 2.7 | HTML 报告 | 检查 `local_data/reports/*.html` | 报告存在且可打开 |

**运行**: `python test_runner.py --phase 2`

**⚠️ 2.6 需要 LLM API Key**。如未配置，该项自动跳过。

---

### Phase 3 — 边界与压力测试 (Edge Cases)

**目标**: 验证系统在非正常输入下的行为。

| # | 测试项 | 输入 | 预期 |
|---|--------|------|------|
| 3.1 | 空参数 | `python kb_query.py` | 显示帮助 |
| 3.2 | 无结果查询 | `"xyzabc不存在" --threshold 0.9` | 返回 ok=true, chunks=[] |
| 3.3 | 特殊字符 | `"α β γ"`, `"E = mc²"` | 正常返回或空结果 |
| 3.4 | 极短文本 | 摄入 1 行文本 | 正常分块摄入 |
| 3.5 | Markdown | 摄入含表格/公式的 .md | 正确处理 Markdown 结构 |
| 3.6 | 分类法配置 | 读取 `CLASSIFICATION_SCHEMES` | 4 个分类法全部有效 |

**运行**: `python test_runner.py --phase 3`

---

## 手动测试步骤

以下测试需要人工观察 UI 或特定设备，无法自动化。

### 4.1 Web UI 测试

```batch
# 启动
cd D:\knowledge-forge
run.bat
```

| # | 测试项 | 操作 | 预期 |
|---|--------|------|------|
| 4.1.1 | 页面加载 | 浏览器打开 `http://localhost:8501` | 显示火焰标题和搜索框 |
| 4.1.2 | 搜索功能 | 输入"齿轮"点击搜索 | 显示搜索结果卡片 |
| 4.1.3 | 问答功能 | 输入"齿轮失效形式"点击问答 | 显示 AI 回答和引用 |
| 4.1.4 | 设置页面 | 侧边栏 → 设置 | API 配置可编辑保存 |
| 4.1.5 | 分类法切换 | 侧边栏切换分类法 | 集合列表变更 |
| 4.1.6 | 摄入面板 | 上传 TXT 文件 | 文件成功摄入 |
| 4.1.7 | 报告下载 | 点击下载按钮 | 下载 HTML/PDF 报告 |
| 4.1.8 | 暗色模式 | 切换系统暗色模式 | UI 自动适配 |

### 4.2 OCR 测试（可选，需 PaddleOCR）

| # | 测试项 | 操作 | 预期 |
|---|--------|------|------|
| 4.2.1 | OCR 识别 | `--ocr test_image.png --check-only` | 输出识别文本 |
| 4.2.2 | OCR 入库 | `--ocr test_image.png --source 手册-P3` | 识别+摄入 |
| 4.2.3 | 结构化 OCR | `--ocr test_image.png --engine structured` | 输出含表格/公式 |
| 4.2.4 | LLM 优化 | `--ocr test_image.png --llm-optimize` | 自动纠错 |

---

## 测试数据文件

| 文件 | 大小 | 用途 |
|------|------|------|
| `test_data/齿轮设计基础.txt` | 2.8KB | 中文技术文档（表格、公式） |
| `test_data/产品运营笔记.txt` | 1.9KB | 中文运营文档（Markdown 表格） |
| `test_data/AI_Research_Notes.md` | 2.9KB | 中英混合技术笔记 |
| `test_data/edge_cases.txt` | 新建 | 特殊字符/公式/嵌套/代码 |
| `test_data/short_text.txt` | 新建 | 极短文本边界测试 |

---

## 快速运行

```bash
# 完整自动化测试（推荐）
cd D:\knowledge-forge
C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe test_data/test_runner.py

# 仅冒烟测试
python test_data/test_runner.py --phase 1

# 仅功能测试
python test_data/test_runner.py --phase 2

# 仅边界测试
python test_data/test_runner.py --phase 3

# 手动启动 Web UI
run.bat
```

---

## 通过标准

- **Phase 1**: 100% 通过（环境不满足则不应继续）
- **Phase 2**: 除 2.6（需要 API Key）外全部通过
- **Phase 3**: 全部通过或合理跳过
- **手动测试**: UI 基本功能正常
