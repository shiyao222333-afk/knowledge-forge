"""
📥 文档注入 — 上传文件 / OCR 图片 / 手动输入 / LLM优化 / 二次编辑
"""

import streamlit as st
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import kb_query
from utils.ui_utils import (
    render_sidebar, cached_stats, cached_collections, save_env, clear_kb_caches,
)
from utils.flame_bg import render_flame_banner

# ── 侧边栏 ──
with st.sidebar:
    render_sidebar()

# ── 标题 ──
st.title("📥 文档注入")
render_flame_banner()

collection = st.session_state.get("active_collection", kb_query.DEFAULT_COLLECTION)
st.markdown(f"向 **{collection}** 知识库中摄入文档。")
st.caption(f"📂 文件目录: {st.session_state.kb_root_path}")

qdrant_info = cached_stats(collection)
if qdrant_info.get("status") != "ok":
    st.error("⚠️ Qdrant 向量数据库未运行，无法摄入。请先启动 `run.bat`。")

# ═══════════════════════════════════════════
# 3 个 Tab: 上传文件 / OCR 图片 / 手动输入
# ═══════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📄 上传文件", "🖼️ OCR 图片", "✏️ 手动输入"])

# ── Tab 1: 上传文件 ──
with tab1:
    st.markdown("#### 上传文件")
    st.markdown("支持 .txt .pdf .md 文件")

    uploaded_file = st.file_uploader(
        "选择文件",
        type=["txt", "pdf", "md", "json"],
        help="上传后自动摄入到知识库",
    )

    if uploaded_file is not None:
        # 保存上传文件
        save_path = os.path.join(st.session_state.kb_root_path, uploaded_file.name)
        parent_dir = os.path.dirname(save_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"✅ 文件已保存：{uploaded_file.name}")

        # 预览
        try:
            preview = uploaded_file.getvalue().decode("utf-8")[:3000]
            with st.expander("📄 文件预览"):
                st.code(preview, language=None)
            if len(uploaded_file.getvalue()) > 3000:
                st.caption(f"... 全文共 {len(uploaded_file.getvalue())} 字符")
        except Exception:
            pass

        # LLM 优化 + 手动编辑
        st.markdown("---")
        use_llm = st.checkbox("🧠 LLM 优化文本（自动修正错别字、格式化）", value=False,
                              help="需要配置 LLM API Key（在引擎配置页面）")

        # 手动编辑区域（仅网页端）
        if use_llm and os.environ.get("KB_LLM_API_KEY"):
            if st.button("🔧 LLM 优化", type="secondary"):
                with st.spinner("LLM 优化中..."):
                    try:
                        text = uploaded_file.getvalue().decode("utf-8")
                        optimized = kb_query._call_llm_api(
                            [{"role": "user", "content": f"请优化以下文本，修正错别字，保持原意不变，直接输出优化后的文本：\n\n{text[:5000]}"}],
                            base_url=os.environ.get("KB_LLM_BASE_URL", ""),
                            api_key=os.environ.get("KB_LLM_API_KEY", ""),
                            model=os.environ.get("KB_LLM_MODEL", ""),
                        )
                        st.session_state.edit_text = optimized
                        st.session_state.file_edit_area = optimized
                        st.rerun()
                    except Exception as e:
                        st.error(f"LLM 优化失败: {e}")
        elif use_llm:
            st.info("💡 需要先在「引擎配置」页面配置 LLM API Key")

        edit_text = st.text_area(
            "📝 手动编辑文本（可选）",
            value=st.session_state.get("edit_text", ""),
            height=300,
            placeholder="LLM 优化后或原始文本，可手动编辑...",
            key="file_edit_area",
        )

        # 摄入按钮
        if st.button("🚀 摄入到知识库", type="primary", use_container_width=True):
            if qdrant_info.get("status") != "ok":
                st.error("⚠️ Qdrant 未运行，请先启动 Qdrant。")
            else:
                progress_bar = st.progress(0, "正在读取文件...")
                time.sleep(0.2)
                progress_bar.progress(30, "正在分块...")
                time.sleep(0.2)

                ingest_text = edit_text.strip() if edit_text.strip() else uploaded_file.getvalue().decode("utf-8")
                result = kb_query.ingest(
                    text=ingest_text,
                    metadata={"source": uploaded_file.name},
                    collection=collection,
                )

                if result.get("ok"):
                    progress_bar.progress(100, "摄入完成！")
                    st.success(f"✅ 摄入成功！共 {result.get('chunks', '?')} 个分块")
                    clear_kb_caches()
                    st.session_state.edit_text = ""
                else:
                    progress_bar.empty()
                    error_msg = result.get("error", "未知错误")
                    if "重复" in error_msg:
                        st.warning(f"⚠️ {error_msg}")
                    else:
                        st.error(f"❌ 摄入失败: {error_msg}")

# ── Tab 2: OCR 图片 ──
with tab2:
    st.markdown("#### OCR 图片识别")
    st.markdown("上传图片，自动识别文字并摄入")

    uploaded_image = st.file_uploader(
        "选择图片",
        type=["png", "jpg", "jpeg", "bmp"],
        help="支持 PaddleOCR 识别",
        key="ocr_uploader",
    )

    llm_optimize = st.checkbox("🧠 LLM 优化识别结果（自动修复错别字）", value=True, key="ocr_llm_check")

    if uploaded_image is not None:
        img_path = os.path.join(st.session_state.kb_root_path, uploaded_image.name)
        parent_dir = os.path.dirname(img_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(img_path, "wb") as f:
            f.write(uploaded_image.getbuffer())

        st.image(img_path, caption="预览", width=300)

        if st.button("🔍 开始 OCR", type="primary"):
            if not os.environ.get("KB_LLM_API_KEY") and llm_optimize:
                st.warning("⚠️ 未配置 LLM API Key，将跳过 OCR 优化")

            progress_bar = st.progress(0, "正在 OCR 识别...")
            try:
                ocr_result = kb_query._ocr_paddle(img_path)
                progress_bar.progress(40, "OCR 完成，正在处理...")

                if ocr_result.get("ok"):
                    text = ocr_result.get("text", "")

                    # LLM 优化（如果启用）
                    edited_text = text
                    if llm_optimize and os.environ.get("KB_LLM_API_KEY") and text.strip():
                        try:
                            optimized = kb_query._call_llm_api(
                                [{"role": "user", "content": f"请优化以下OCR识别结果，修正错别字，保持原意不变，直接输出优化后的文本：\n\n{text[:5000]}"}],
                                base_url=os.environ.get("KB_LLM_BASE_URL", ""),
                                api_key=os.environ.get("KB_LLM_API_KEY", ""),
                                model=os.environ.get("KB_LLM_MODEL", ""),
                            )
                            if optimized.strip():
                                edited_text = optimized
                                st.caption("✅ 已用 LLM 优化识别结果")
                        except Exception:
                            pass

                    st.markdown("#### 识别结果：")
                    st.text_area("OCR 输出", text, height=200, disabled=True, key="ocr_output")
                    st.caption(
                        f"置信度: {ocr_result.get('conf', 'N/A')} | "
                        f"字符数: {ocr_result.get('chars', 0)}"
                    )

                    # 编辑区域
                    edited = st.text_area("📝 手动编辑（可选）", value=edited_text, height=200, key="ocr_edit")

                    progress_bar.progress(70, "正在摄入向量库...")

                    if qdrant_info.get("status") == "ok":
                        result = kb_query.ingest(
                            text=edited.strip() or text,
                            metadata={"source": uploaded_image.name},
                            collection=collection,
                        )
                        if result.get("ok"):
                            progress_bar.progress(100, "完成！")
                            st.success(f"✅ OCR + 摄入完成！共 {result.get('chunks', '?')} 个分块")
                            clear_kb_caches()
                        else:
                            progress_bar.empty()
                            st.warning(f"OCR 成功但摄入失败: {result.get('error')}")
                    else:
                        progress_bar.progress(100, "OCR 完成（未摄入）")
                        st.warning("⚠️ Qdrant 未运行，OCR 结果未入库")
                else:
                    progress_bar.empty()
                    st.error(f"OCR 失败: {ocr_result.get('error', '未知错误')}")
            except Exception as e:
                progress_bar.empty()
                st.error(f"OCR 出错: {e}")

# ── Tab 3: 手动输入 ──
with tab3:
    st.markdown("#### 手动输入文本")
    st.markdown("直接粘贴文本内容，手动摄入")

    manual_text = st.text_area(
        "输入文本内容",
        height=300,
        placeholder="把你的笔记、想法、资料粘贴到这里...",
        key="manual_input",
    )

    source_name = st.text_input(
        "来源标识（可选）",
        placeholder="例如：我的笔记、齿轮手册P23",
        key="manual_source",
    )

    # LLM 优化
    use_llm_manual = st.checkbox("🧠 LLM 优化", value=False, key="manual_llm")
    if use_llm_manual and os.environ.get("KB_LLM_API_KEY") and manual_text.strip():
        if st.button("🔧 运行优化", type="secondary", key="manual_optimize"):
            with st.spinner("LLM 优化中..."):
                try:
                    optimized = kb_query._call_llm_api(
                        [{"role": "user", "content": f"请优化以下文本，修正错别字，保持原意不变，直接输出优化后的文本：\n\n{manual_text[:5000]}"}],
                        base_url=os.environ.get("KB_LLM_BASE_URL", ""),
                        api_key=os.environ.get("KB_LLM_API_KEY", ""),
                        model=os.environ.get("KB_LLM_MODEL", ""),
                    )
                    st.text_area("优化结果（可编辑）", value=optimized, height=200, key="manual_optimized")
                except Exception as e:
                    st.error(f"LLM 优化失败: {e}")

    if st.button("💾 保存到知识库", type="primary", use_container_width=True, key="manual_save"):
        if not manual_text.strip():
            st.warning("⚠️ 请输入文本内容")
        elif qdrant_info.get("status") != "ok":
            st.error("⚠️ Qdrant 未运行，请先启动 Qdrant。")
        else:
            progress_bar = st.progress(0, "正在分块...")
            time.sleep(0.2)
            progress_bar.progress(40, "正在嵌入向量...")

            # 优先使用 LLM 优化后的文本，否则用原始输入
            ingest_text = st.session_state.get("manual_optimized", "").strip() or manual_text
            result = kb_query.ingest(
                text=ingest_text,
                metadata={"source": source_name or "手动输入"},
                collection=collection,
            )
            progress_bar.progress(100, "完成！")

            if result.get("ok"):
                st.success(f"✅ 保存成功！共 {result.get('chunks', '?')} 个分块")
                clear_kb_caches()
            else:
                progress_bar.empty()
                error_msg = result.get("error", "未知错误")
                if "重复" in error_msg:
                    st.warning(f"⚠️ {error_msg}")
                else:
                    st.error(f"❌ 保存失败: {error_msg}")
