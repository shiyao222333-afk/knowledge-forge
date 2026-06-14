<p align="center">
  <img src="assets/logo.svg" alt="KnowledgeForge Logo" width="120" height="120">
</p>

<h1 align="center">🔥 KnowledgeForge / 知炬</h1>

<p align="center">
  <b>个人本地知识引擎</b><br>
  把截图、手册、笔记丢进去，问一个问题，直接得到<strong>带来源引用的答案</strong>。<br>
  数据全在本地，不联网也能用。
</p>

<p align="center">
  <a href="https://github.com/shiyao222333-afk/knowledge-forge"><img src="https://img.shields.io/badge/Python-3.13+-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+"></a>
  <img src="https://img.shields.io/badge/Status-Active-green?style=flat-square" alt="Active">
  <img src="https://img.shields.io/badge/Stage-MVP-orange?style=flat-square" alt="MVP">
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/blob/main/LICENSE"><img src="https://img.shields.io/github/license/shiyao222333-afk/knowledge-forge?style=flat-square" alt="MIT License"></a>
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/stargazers"><img src="https://img.shields.io/github/stars/shiyao222333-afk/knowledge-forge?style=social" alt="Stars"></a>
</p>

<p align="center">
  <a href="#-3秒快速体验"><b>⚡ 3秒体验</b></a> ·
  <a href="#-为什么需要-knowledgeforge"><b>🤔 为什么需要</b></a> ·
  <a href="#-核心特性"><b>✨ 核心特性</b></a> ·
  <a href="#-适合谁用"><b>👤 适合谁用</b></a> ·
  <a href="#-路线图"><b>🗺️ 路线图</b></a> ·
  <a href="#-与类似工具对比"><b>🆚 工具对比</b></a> ·
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/issues"><b>🐛 提 Issue</b></a>
</p>

---

## 🤔 为什么需要 KnowledgeForge？

> **"有问题直接问 LLM（GPT/DeepSeek）不就行了，为什么要手动输入知识，这么麻烦？"**

这是最重要的问题。答案一句话：

> **LLM 是"聪明的外人"，KnowledgeForge 是"读过你所有资料的私人助理"。**

| 问题 | 直接问 LLM | 用 KnowledgeForge |
|------|-----------|-------------------|
| 没有你的私有知识 | ❌ 它没读过 | ✅ 直接搜你本地资料 |
| 没有记忆 | ❌ 每次对话都是新的 | ✅ 越用越强 |
| 无法溯源 | ❌ 答案不知道从哪来 | ✅ 每个答案带 `[引用N]` |
| 数据隐私 | ❌ 上传云端 | ✅ 全本地运行 |

---

## ⚡ 3秒快速体验

```bash
# 1. 克隆项目
git clone https://github.com/shiyao222333-afk/knowledge-forge.git
cd knowledge-forge

# 2. 安装依赖
pip install -r requirements.txt   # 或直接用 uv/poetry

# 3. 一键启动（Windows）
.\run.bat
# macOS/Linux
chmod +x run.sh && ./run.sh

# 4. 浏览器自动打开 http://localhost:8501
#    跟着向导建库 → 上传文件 → 开始提问！
```

> 💡 需要有 LLM API Key（DeepSeek / 通义千问 等均可），在「引擎配置」页面一键填写。

---

## ✨ 核心特性

<div align="center">

| 特性 | 说明 |
|------|------|
| 🔍 **语义搜索** | AI 理解意图，不是关键词匹配 |
| 📸 **截图识别** | PaddleOCR 识别截图/照片文字 |
| 📊 **表格精确引用** | 大表格按行拆分，精确到行 |
| 🔗 **引用溯源** | 每个回答标注 `[引用N]`，可点击跳转 |
| 📐 **公式渲染** | PPStructureV3 识别 → KaTeX 渲染 |
| 🏠 **全本地运行** | 数据不出门，隐私有保障 |
| 🤖 **LLM OCR 优化** | 自动修复 OCR 错别字 |
| 🌐 **Web UI** | 多页面 Streamlit 界面，开箱即用 |

</div>

---

## 💻 界面预览

```
KnowledgeForge Web UI（v0.2 MVP）
┌──────────┬──────────────────────────────┐
│ 📥 文档注入 │ 上传文件 / OCR / 手动输入      │
│ 💬 智能检索 │ 搜索 + AI 问答，跨库检索      │
│ 🗂️ 知识中枢 │ 建库 / 管理 / 重建 / 导出    │
│ ⚙️ 引擎配置 │ LLM + 嵌入模型 + 系统设置     │
└──────────┴──────────────────────────────┘
```

> 📸 **截图待补充**：启动后对着界面截一张图，放到 `docs/screenshot.png`，然后取消下面注释。

<!-- 取消注释后生效：
<p align="center">
  <img src="docs/screenshot.png" alt="Web UI 截图" width="800">
</p>
-->

---

## 👤 适合谁用？

| ✅ 非常适合 | ❌ 不太适合 |
|--------------|--------------|
| 有中文/英文技术文档/手册积累的人 | 数据量极小（<10 个文件）且不需要搜索 |
| 截图/照片里有大量文字想搜 | 想要完整商业化 Web UI（我们还在迭代） |
| 关心数据隐私，不想上传云端 | 不想碰任何配置（首次需 2 分钟配置） |
| 需要溯源：答案从哪来的 | |
| 公式/表格很多的技术文档 | |
| 网文作者（世界观设定管理） | |

---

## 💡 6 个真实使用场景

<details>
<summary><b>场景一：内容创作者的「灵感库」</b>（点击展开）</summary>

**典型用户**：B站UP主、小红书博主、公众号写手  
**痛点**：素材散落在微信收藏、浏览器书签、手机截图、笔记软件里  
**用法**：把素材全部摄入 → 写作时问"帮我找一下之前关于『修仙小说开篇技巧』的资料"

</details>

<details>
<summary><b>场景二：技术人的「私有文档搜索」</b></summary>

**典型用户**：程序员、工程师  
**痛点**：技术手册、API文档、自己写的笔记，搜起来很麻烦  
**用法**：把 PDF 手册、个人笔记全部摄入 → 问"React useEffect 第二个参数怎么用？"

</details>

<details>
<summary><b>场景三：小说创作的「世界观库」</b></summary>

**典型用户**：网文作者（你的独特场景！）  
**痛点**：写小说需要查设定、保持一致性，设定文档几千字，翻起来很麻烦  
**用法**：把修仙设定文档、人物关系表全部摄入 → 问"主角的灵根属性是什么？"

</details>

> 更多场景见 [场景四~六](https://github.com/shiyao222333-afk/knowledge-forge/blob/main/README.md#场景四打工人的工作任务库)（学生/打工人/爱好者的用法）

---

## 🆚 与类似工具对比

| 功能 | KnowledgeForge | RAGFlow | AnythingLLM | Dify | FastGPT |
|------|:---------------:|:-------:|:-----------:|:----:|:-------:|
| 中文优化 | ✅ | ✅ | ✅ | ✅ | ✅ |
| OCR 识别 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 公式渲染 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 表格行级拆分 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 引用连续编号 | ✅ | ❌ | ❌ | ❌ | ❌ |
| LLM OCR 优化 | ✅ | ❌ | ❌ | ❌ | ❌ |
| Web UI | ✅ v0.2 | ✅ | ✅ | ✅ | ✅ |
| 完全本地运行 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 部署难度 | 低 | 中 | 低 | 高 | 中 |

> **选择建议**：需要处理**中文技术文档、公式、表格** → **KnowledgeForge**

---

## 🏗️ 架构概览

```
KnowledgeForge（分层架构）

┌─────────────────────────────────────────────┐
│  用户层：Web UI（Streamlit 多页面）          │
├─────────────────────────────────────────────┤
│  服务层：问答合成 · 引用管理 · 报告生成    │
├─────────────────────────────────────────────┤
│  核心层：向量检索 · OCR · 嵌入 · 分类      │
├─────────────────────────────────────────────┤
│  存储层：Qdrant（向量）· 文件系统         │
└─────────────────────────────────────────────┘
```

**技术栈**：
- 向量数据库：[Qdrant](https://github.com/qdrant/qdrant)
- 嵌入模型：[Ollama](https://github.com/ollama/ollama) + `qwen3-embedding:4b`
- OCR 引擎：[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) / PPStructureV3
- LLM 合成：OpenAI 兼容 API（默认 DeepSeek）
- 公式渲染：[KaTeX](https://github.com/KaTeX/KaTeX)
- Web UI：[Streamlit](https://streamlit.io) 1.58+

---

## 🗺️ 路线图

### ✅ v0.1 — 核心引擎（已完成）
- [x] 向量搜索 + LLM 问答
- [x] OCR 识别（PaddleOCR）
- [x] 公式识别与渲染
- [x] 表格行级拆分
- [x] 引用连续编号
- [x] LLM OCR 优化

### ✅ v0.2 — Web UI MVP（已完成 🎉）
- [x] Streamlit 多页面架构
- [x] 文档注入（上传/OCR/手动 + LLM 优化 + 手动编辑）
- [x] 智能检索（搜索 + AI 问答 + 跨库多选）
- [x] 知识中枢（卡片仪表盘 + 建库向导 + 管理操作）
- [x] 引擎配置（LLM 预设 + 嵌入模型管理）

### 🔄 v0.3 — 完善体验（规划中）
- [ ] 文件预览 + 在线编辑
- [ ] 多知识库权限管理
- [ ] 微信 Bot 对接（手机端输入）
- [ ] 守望文件夹自动摄入
- [ ] 摄入日志可视化

### 🔮 v0.4 ~ v0.5 — 知识图谱 + 多模态
- [ ] 自动建立知识点关联
- [ ] 图表理解
- [ ] 手写笔记 OCR
- [ ] 本地 LLM 推理

---

## ⚙️ 快速开始

### 1. 环境准备

```bash
# Python >= 3.13
# Ollama（嵌入模型运行环境）从 https://ollama.com 安装

# 拉取嵌入模型
ollama pull qwen3-embedding:4b
```

### 2. 安装 Python 依赖

```bash
pip install streamlit requests qdrant-client \
            paddlepaddle paddleocr "paddlex[ocr]==3.7.0" \
            fpdf2 pillow matplotlib
```

### 3. 启动

```bash
# Windows
.\run.bat

# macOS / Linux
./run.sh   # （待创建，目前用 streamlit run app.py）
```

浏览器访问 `http://localhost:8501`

---

## 📖 使用指南

启动后按照向导操作：

1. **首次使用** → 自动弹出建库向导（选择分类法 → 选择嵌入模型 → 创建集合）
2. **摄入资料** → 进入「文档注入」页面，上传文件或 OCR 图片
3. **搜索问答** → 进入「智能检索」页面，输入问题，勾选是否用 AI
4. **管理知识库** → 进入「知识中枢」页面，查看统计、重建、导出

详细文档见 [START.md](START.md)。

---

## 🤝 贡献指南

欢迎参与！这个项目处于活跃开发阶段，每一份贡献都能显著影响方向。

- 🐛 **报告 Bug**：[提交 Issue](https://github.com/shiyao222333-afk/knowledge-forge/issues/new)
- 💡 **提议新功能**：[功能请求](https://github.com/shiyao222333-afk/knowledge-forge/issues/new?template=feature)
- 💻 **提交代码**：Fork → 分支 → PR
- 📖 **完善文档**：使用案例、最佳实践

---

## ❓ FAQ

**Q：支持英文文档吗？**  
A：支持。`qwen3-embedding:4b` 对中英文都有效果。英文场景建议换用 `nomic-embed-text`。

**Q：能处理多少数据？**  
A：理论上无上限，受限于硬件。Qdrant 支持磁盘存储。建议先从小批量（几十个文件）开始测试。

**Q：和 Obsidian / Notion 有什么区别？**  
A：Obsidian 是笔记管理，Notion 是在线协作。KnowledgeForge 专注**非结构化资料**（截图、扫描件、PDF）的**语义搜索和问答**。

**Q：需要联网吗？**  
A：摄入和搜索不需要联网。只有调用 LLM 合成回答时需要联网（可以切换为本地 LLM 来完全离线）。

---

## 📄 许可证

[MIT License](LICENSE) - 自由使用、修改和分发。

---

## 🙏 致谢

- [Qdrant](https://github.com/qdrant/qdrant) - 向量数据库
- [Ollama](https://github.com/ollama/ollama) - 本地嵌入模型运行环境
- [KaTeX](https://github.com/KaTeX/KaTeX) - 公式渲染
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - 中文 OCR

---

<p align="center">
  ⭐ 如果这个方向对你有启发，请给一个 Star！<br>
  🗂️ 让每个人的知识积累，都变成真正的资产。
</p>

<p align="center">
  <img src="https://api.star-history.com/svg?repos=shiyao222333-afk/knowledge-forge&type=Date&width=600&height=200" alt="Star History Chart">
</p>
