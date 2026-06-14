"""
💬 智能检索 — 语义搜索 + AI 问答合并，勾选是否用 LLM，跨库搜索
"""

import streamlit as st
import os
import sys
import html as html_mod

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import kb_query
from utils.ui_utils import (
    render_sidebar, cached_stats, cached_collections,
)
from utils.flame_bg import render_flame_banner

# ── 侧边栏 ──
with st.sidebar:
    render_sidebar()

# ── 标题 ──
st.title("💬 智能检索")
render_flame_banner()

collection = st.session_state.get("active_collection", kb_query.DEFAULT_COLLECTION)
qdrant_info = cached_stats(collection)
if qdrant_info.get("status") != "ok":
    st.error("⚠️ Qdrant 未运行，无法搜索。请先启动 `run.bat`。")

# ── 知识库多选 ──
col_data = cached_collections()
all_cols = [c["name"] for c in col_data.get("collections", [])] if col_data.get("ok") else [collection]
if all_cols:
    selected_cols = st.multiselect(
        "📚 搜索范围",
        options=all_cols,
        default=[collection] if collection in all_cols else [all_cols[0]],
        help="选择要搜索的知识库。可多选实现跨库搜索。",
    )
else:
    selected_cols = []

# ── 输入框 ──
query = st.text_input(
    "输入问题或关键词",
    placeholder="例如：齿轮的失效形式有哪些？",
    label_visibility="collapsed",
    key="search_query",
)

# ── 控制栏 ──
col1, col2, col3 = st.columns([2, 1, 3])

with col1:
    use_llm = st.checkbox("🤖 使用 AI 综合回答", value=False,
                          help="勾选后将先搜索知识库，再调用 LLM 综合成答案。不勾选只显示原始搜索结果。")

with col2:
    top_k = st.selectbox("返回条数", [3, 5, 10, 20], index=1, key="search_top_k")

with col3:
    search_btn = st.button("🔍 开始检索", type="primary", use_container_width=True)

# ── 搜索逻辑 ──
if search_btn and query.strip():
    if qdrant_info.get("status") != "ok":
        st.error("⚠️ Qdrant 未运行。")
    elif not selected_cols:
        st.warning("⚠️ 没有可选的知识库。")
    else:
        if use_llm:
            if not os.environ.get("KB_LLM_API_KEY"):
                st.error("⚠️ 未配置 LLM API Key，请先到「引擎配置」页面配置。")
            else:
                with st.spinner("🔍 搜索 + AI 合成中..."):
                    if len(selected_cols) == 1:
                        result = kb_query.answer(
                            query=query.strip(),
                            top_k=top_k,
                            collection=selected_cols[0],
                            llm_api_key=os.environ.get("KB_LLM_API_KEY", ""),
                            llm_base_url=os.environ.get("KB_LLM_BASE_URL", ""),
                            llm_model=os.environ.get("KB_LLM_MODEL", ""),
                        )
                    else:
                        result = kb_query.answer(
                            query=query.strip(),
                            top_k=top_k,
                            collection=selected_cols[0],
                            llm_api_key=os.environ.get("KB_LLM_API_KEY", ""),
                            llm_base_url=os.environ.get("KB_LLM_BASE_URL", ""),
                            llm_model=os.environ.get("KB_LLM_MODEL", ""),
                            search_mode="multi",
                            search_collections=selected_cols,
                        )
                st.session_state.last_answer = result
        else:
            with st.spinner("🔍 搜索中..."):
                if len(selected_cols) == 1:
                    result = kb_query.search(
                        query=query.strip(),
                        top_k=top_k,
                        collection=selected_cols[0],
                    )
                else:
                    result = kb_query.search_multi(
                        query=query.strip(),
                        top_k=top_k,
                        collections=selected_cols,
                    )
            st.session_state.last_search = result
            st.session_state.last_answer = None

# ── 渲染结果 ──
# AI 问答结果
if st.session_state.get("last_answer"):
    result = st.session_state.last_answer
    st.markdown("---")
    if not result.get("ok"):
        st.error(f"❌ {result.get('error', '请求失败')}")
    else:
        synthesis = result.get("synthesis", "")
        chunks = result.get("chunks", [])

        st.markdown("### 🤖 AI 综合回答")
        st.markdown(f"""
        <div class="kf-answer-card" style="white-space:pre-wrap">
            {html_mod.escape(synthesis)}
        </div>
        """, unsafe_allow_html=True)

        if chunks:
            st.markdown("---")
            st.markdown(f"### 📚 引用来源（共 {len(chunks)} 条）")
            for i, chunk in enumerate(chunks):
                score = chunk.get("score", 0)
                source = chunk.get("source", "未知")
                text = chunk.get("text", "")[:300]
                with st.expander(f"[{i+1}] {source} — 相关度 {score:.2f}"):
                    st.markdown(f"""
                    <div class="kf-score-bar" style="width:{int(score*100)}%"></div>
                    """, unsafe_allow_html=True)
                    if source and source != "未知":
                        st.caption(f"📄 来源: {source}")
                    st.markdown(f"**内容**：{text}")

        # 下载报告
        html_path = result.get("html")
        pdf_path = result.get("pdf")
        has_report = (html_path and os.path.exists(html_path))
        if has_report:
            st.markdown("---")
            dl_col1, dl_col2 = st.columns(2)
            if html_path and os.path.exists(html_path):
                with dl_col1:
                    with open(html_path, "r", encoding="utf-8") as f:
                        st.download_button(
                            "📥 下载 HTML 报告",
                            f.read(),
                            file_name=os.path.basename(html_path),
                            mime="text/html",
                            use_container_width=True,
                        )
            if pdf_path and os.path.exists(pdf_path):
                with dl_col2:
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "📥 下载 PDF 报告",
                            f.read(),
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf",
                            use_container_width=True,
                        )

# 纯搜索结果
elif st.session_state.get("last_search"):
    sr = st.session_state.last_search
    st.markdown("---")
    if not sr.get("ok"):
        st.error(f"❌ 搜索失败: {sr.get('error', '未知错误')}")
    else:
        chunks = sr.get("chunks", [])
        if not chunks:
            st.info("📭 未找到相关内容，请尝试更换关键词。")
        else:
            st.markdown(f"### 📋 搜索结果（共 {len(chunks)} 条）")
            for i, chunk in enumerate(chunks):
                score = chunk.get("score", 0)
                source = chunk.get("source", "未知")
                text = chunk.get("text", "")
                with st.expander(f"[{i+1}] {source} — 相关度 {score:.2f}"):
                    st.markdown(f"""
                    <div class="kf-score-bar" style="width:{int(score*100)}%"></div>
                    """, unsafe_allow_html=True)
                    if source and source != "未知":
                        st.caption(f"📄 来源: {source}")
                    st.markdown(text)
