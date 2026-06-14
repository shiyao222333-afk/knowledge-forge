"""
📹 关于 KnowledgeForge / 知炬
用于视频演示的更新日志与项目介绍页面
"""

import streamlit as st
import json
from pathlib import Path

st.set_page_config(
    page_title="关于 - KnowledgeForge",
    page_icon="📹",
    layout="wide",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .about-hero {
        text-align: center;
        padding: 40px 20px 30px;
        background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
        border-radius: 16px;
        margin-bottom: 30px;
        border: 1px solid #30363d;
    }
    .about-hero h1 {
        font-size: 2.4rem;
        color: #FF6B35;
        margin-bottom: 8px;
    }
    .about-hero p {
        color: #8b949d;
        font-size: 1.1rem;
    }
    .version-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
    }
    .version-card h3 {
        color: #FF6B35;
        margin-bottom: 12px;
    }
    .version-card.done { border-left: 4px solid #00CC66; }
    .version-card.current { border-left: 4px solid #FF6B35; }
    .version-card.plan { border-left: 4px solid #58a6ff; }
    .changelog-item {
        padding: 6px 0;
        color: #c9d1d9;
        font-size: 0.95rem;
    }
    .changelog-item::before {
        content: "✅ ";
        color: #00CC66;
    }
    .stat-grid {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        justify-content: center;
        margin: 20px 0;
    }
    .stat-card {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 20px;
        min-width: 140px;
        text-align: center;
    }
    .stat-number {
        font-size: 2rem;
        font-weight: bold;
        color: #FF6B35;
    }
    .stat-label {
        font-size: 0.85rem;
        color: #8b949d;
        margin-top: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 顶部 Hero ──────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="about-hero">
        <h1>🔥 KnowledgeForge / 知炬</h1>
        <p>个人本地知识引擎 — 把截图、手册、笔记丢进去，问一个问题，直接得到带来源引用的答案。</p>
        <p style="margin-top: 12px; font-size: 0.9rem;">数据全在本地，不联网也能用。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 项目统计 ────────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown('<div class="stat-card"><div class="stat-number">4</div><div class="stat-label">核心页面</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div class="stat-card"><div class="stat-number">3</div><div class="stat-label">发展阶段</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown('<div class="stat-card"><div class="stat-number">8+</div><div class="stat-label">核心特性</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown('<div class="stat-card"><div class="stat-number">100%</div><div class="stat-label">本地运行</div></div>', unsafe_allow_html=True)

st.divider()

# ── 更新日志 ──────────────────────────────────────────────────────────────────
st.markdown("## 📋 更新日志")

# v0.2 - 当前版本
with st.container():
    st.markdown('<div class="version-card current">', unsafe_allow_html=True)
    st.markdown("### 🔵 v0.2 — Web UI MVP（当前版本）")
    st.caption("2026-06-14 发布")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**新增功能**")
        changelog = [
            "Streamlit 多页面架构（文档注入 / 智能检索 / 知识中枢 / 引擎配置）",
            "文档注入：上传 / OCR / 手动输入 + LLM 优化 + 手动编辑",
            "智能检索：搜索 + AI 问答合并，支持跨库多选",
            "知识中枢：卡片仪表盘 + 首次建库向导 + 集合管理",
            "引擎配置：LLM 预设（5 个）+ 在线获取模型 + 嵌入模型管理",
            "st.dialog 原生弹窗确认（清空 / 删除操作）",
            "缓存优化：精确清理替代全量清除",
            "像素火焰背景动画（欢迎页）",
        ]
        for item in changelog:
            st.markdown(f'<div class="changelog-item">{item}</div>', unsafe_allow_html=True)
    
    with col_b:
        st.markdown("**技术改进**")
        tech_items = [
            "核心逻辑（kb_query.py）与 UI 层完全分离",
            "面向未来手机端：三种交互方式规划（Bot / App / 守望文件夹）",
            "配置用环境变量 + .env，路径用相对路径",
            "README.md 全面美化 + 项目 Logo",
            "Bug 修复：8 个严重 + 7 个重要",
        ]
        for item in tech_items:
            st.markdown(f'<div class="changelog-item">{item}</div>', unsafe_allow_html=True)
    
    st.markdown("**已知问题**")
    st.warning("⚠️ 守望文件夹自动摄入 — 规划中，尚未实现")
    st.warning("⚠️ 微信 Bot 对接 — 规划中，尚未实现")
    st.warning("⚠️ 文件预览在线编辑 — 规划中，当前仅网页端支持")
    st.markdown('</div>', unsafe_allow_html=True)

# v0.1 - 已完成的
with st.container():
    st.markdown('<div class="version-card done">', unsafe_allow_html=True)
    st.markdown("### 🟢 v0.1 — 核心引擎（已完成）")
    st.caption("2026-06 前发布")
    
    done_items = [
        "向量搜索 + LLM 问答（端到端）",
        "OCR 识别（PaddleOCR / PPStructureV3）",
        "公式识别与 KaTeX 渲染",
        "表格行级拆分引用",
        "引用连续编号（后处理重编号）",
        "LLM OCR 优化（自动修复错别字）",
        "CLI 入口（kb_query.py）",
        "IAM 知识库同步脚本",
    ]
    for item in done_items:
        st.markdown(f'<div class="changelog-item">{item}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# v0.3 - 规划中
with st.container():
    st.markdown('<div class="version-card plan">', unsafe_allow_html=True)
    st.markdown("### 🔷 v0.3 — 完善体验（规划中）")
    st.caption("预计 2026-Q3")
    
    plan_items = [
        "📸 文件预览 + 在线编辑",
        "📁 多知识库权限管理",
        "📱 微信 Bot 对接（手机端输入）",
        "📂 守望文件夹自动摄入",
        "📊 摄入日志可视化",
        "🔗 知识图谱雏形（实体关联）",
    ]
    for item in plan_items:
        st.markdown(f'<div class="changelog-item">{item}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ── 使用流程（用于视频演示）──────────────────────────────────────────────────
st.markdown("## 🎬 使用流程（视频演示指南）")

flow_steps = [
    ("1️⃣ 首次启动", "运行 `python -m streamlit run app.py`，自动打开浏览器\n检测到无知识库 → 弹出建库向导"),
    ("2️⃣ 建库向导", "选择分类法（机械设计 / 材料科学 / 自定义...\n选择嵌入模型（qwen3-embedding 推荐）\n输入集合名称 → 创建"),
    ("3️⃣ 文档注入", "进入「📥 文档注入」页面\n上传文件 / OCR 图片 / 手动输入文本\nLLM 自动优化 + 可手动编辑 → 点击摄入"),
    ("4️⃣ 智能检索", "进入「💬 智能检索」页面\n输入问题 → 勾选「使用 AI 综合回答」\n查看搜索结果 / AI 回答 + 引用来源"),
    ("5️⃣ 知识管理", "进入「🗂️ 知识中枢」页面\n查看集合统计卡片\n切换 / 清空 / 删除集合\n重建（从日志） / 导出备份"),
    ("6️⃣ 引擎配置", "进入「⚙️ 引擎配置」页面\n选择 LLM 预设（DeepSeek / Qwen...）\n在线获取模型列表\n管理嵌入模型（下载 / 删除）"),
]

for step_emoji, (title, desc) in enumerate(flow_steps):
    with st.expander(f"{step_emoji} {title}"):
        st.markdown(desc)
        if step_emoji == 0:
            st.code("cd D:\\knowledge-forge\npython -m streamlit run app.py", language="bash")
        elif step_emoji == 3:
            st.caption("💡 提示：跨库搜索支持多选集合")

st.divider()

# ── 技术架构 ──────────────────────────────────────────────────────────────────
st.markdown("## 🏗️ 技术架构")

arch_cols = st.columns(4)
layers = [
    ("用户层", ["Streamlit Web UI", "命令行 CLI", "（规划）微信 Bot", "（规划）手机 App"]),
    ("服务层", ["问答合成", "引用管理", "报告生成（HTML/PDF）", "分类引擎"]),
    ("核心层", ["向量检索（Qdrant）", "OCR（PaddleOCR）", "嵌入（Ollama）", "LLM 合成"]),
    ("存储层", ["Qdrant 向量库", "文件系统", "摄入日志", "（规划）知识图谱"]),
]
for col, (layer_name, items) in zip(arch_cols, layers):
    with col:
        st.markdown(f"**{layer_name}**")
        for item in items:
            st.markdown(f"- {item}")

st.divider()

# ── 开源协议 & 链接 ───────────────────────────────────────────────────────────
st.markdown("## 📄 开源协议 & 链接")
link_cols = st.columns(3)
with link_cols[0]:
    st.markdown("**项目地址**")
    st.markdown("- [GitHub 仓库](https://github.com/shiyao222333-afk/knowledge-forge)")
    st.markdown("- [Issue 追踪](https://github.com/shiyao222333-afk/knowledge-forge/issues)")
with link_cols[1]:
    st.markdown("**文档**")
    st.markdown("- [完整 README](https://github.com/shiyao222333-afk/knowledge-forge#readme)")
    st.markdown("- [启动说明](START.md)")
with link_cols[2]:
    st.markdown("**协议**")
    st.markdown("- MIT License")
    st.markdown("- 自由使用、修改和分发")

st.caption("KnowledgeForge / 知炬 · 让每个人的知识积累，都变成真正的资产。")
