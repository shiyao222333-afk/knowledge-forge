# WorkBuddy 知识库引擎

基于 **Qdrant 向量库 + Ollama 嵌入 + LLM API 合成** 的中文技术文档知识库问答系统。

## ✨ 功能特性

- **OCR 摄入**：PaddleOCR / PPStructureV3（公式+表格+图表结构化识别）
- **向量搜索**：Qdrant + qwen3-embedding:4b（2560 维）
- **LLM 合成**：DeepSeek API（OpenAI 兼容接口），支持引用标注 + `[补充]` 标记
- **引用粒度控制**：大表格按行拆分为独立引用，避免引用范围过大
- **引用重编号**：回答中实际使用的引用自动重编号为连续 1~N
- **公式渲染**：KaTeX 服务端批量渲染，HTML 打开即用（无 JS 实时计算）
- **HTML 报告**：双层结构（AI 回答 + 原始素材），支持打印/PDF
- **去重过滤**：入库前 SHA256 去重；搜索结果同源去重 + OCR 质量过滤

## 🏗️ 架构

```
摄入: 图片/文本 → PaddleOCR/PPStructureV3 → 分块嵌入 → Qdrant
查询: 自然语言 → 向量搜索 → LLM API 合成 → 程序渲染 HTML/PDF
```

## 📦 安装依赖

```bash
# Python 环境
pip install requests fpdf2 pillow

# PaddleOCR（中文 OCR）
pip install paddlepaddle paddleocr

# PPStructureV3（结构化识别，可选）
pip install "paddlex[ocr]==3.7.0"

# Ollama（嵌入模型运行环境）
# 从 https://ollama.com 安装，然后：
ollama pull qwen3-embedding:4b

# KaTeX（公式渲染，需要 Node.js）
npm install -g katex
```

## 🚀 快速开始

### 1. 启动服务

```bash
# 启动 Qdrant + Ollama（Windows）
.\start.bat
```

### 2. 摄入文档

```bash
# 摄入文本文件
python kb_query.py --ingest "D:/Documents/KnowledgeBase/齿轮设计基础.txt"

# OCR 图片（自动识别公式/表格）
python kb_query.py --ocr "photo.jpg" --source "手册-P3"

# OCR 后先审核再入库
python kb_query.py --ocr "photo.jpg" --check-only
```

### 3. 问答

```bash
# 端到端问答（搜索 → LLM 合成 → HTML 报告）
python kb_query.py "齿轮的失效形式有哪些" --answer --llm-api-key sk-xxx

# 纯搜索（不调用 LLM）
python kb_query.py "齿轮参数表" --top 10
```

## ⚙️ 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `KB_LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `KB_LLM_API_KEY` | LLM API Key | （必须自行设置） |
| `KB_LLM_MODEL` | LLM 模型名 | `deepseek-chat` |

### 命令行参数

#### `--table-split-threshold N`
表格行数 > N 时按行拆分为独立引用（默认 4）。

```bash
python kb_query.py "转动惯量公式" --answer --table-split-threshold 3
```

#### `--threshold F`
搜索相关度阈值（默认 0.3）。

## 📊 输出格式

### HTML 报告结构

```
┌─────────────────────────────────┐
│  📝 综合回答（AI 合成）           │
│  - 引用编号高亮 + 跳转锚点      │
│  - 公式 KaTeX 渲染             │
│  - [补充] 标记                  │
├─────────────────────────────────┤
│  📚 原始素材（逐条展示）       │
│  - 被引用的行显示 [引用N] 标签 │
│  - 未引用的行正常展示（无标签）│
│  - 图片 base64 嵌入            │
└─────────────────────────────────┘
```

## 🔍 引用系统

### 引用粒度

- **默认**：每个搜索结果块作为一条引用 `[引用1]` `~` `[引用N]`
- **大表格**：行数 > 4 时自动按行拆分，每行生成独立引用

### 引用重编号

LLM 回答中实际使用的引用编号会被重编号为连续 1~N，避免编号跳跃。

示例：
```
LLM 输出: "根据[引用5]和[引用2]，结果是[引用3]"
重编号后: "根据[引用1]和[引用2]，结果是[引用3]"
```

### `[补充]` 标记

LLM 在回答中使用非知识库内容时，需在句末标注 `[补充]`。

## 📐 公式支持

- **行内公式**：`$...$`（如 `$J=\frac{\pi\rho D^4}{32}$`）
- **独行公式**：`$$...$$`
- **渲染方式**：KaTeX 服务端批量渲染（HTML 打开即用，无闪烁）

## 📋 文件结构

```
kb_query.py        主程序（OCR/搜索/合成/报告）
render_math.js      Node.js 脚本（KaTeX 渲染）
start.bat          Windows 启动脚本（Qdrant + Ollama）
.gitignore          排除本地数据/日志
```

## 🔧 依赖版本

| 依赖 | 版本 |
|---|---|
| Python | 3.13+ |
| requests | 2.31+ |
| fpdf2 | 2.8+ |
| PaddleOCR | 3.7+ |
| Ollama | 0.7+ |
| qwen3-embedding | 4b（2560 维）|
| Node.js | 22+ |
| KaTeX | 0.16+ |

## 📄 许可证

MIT License
