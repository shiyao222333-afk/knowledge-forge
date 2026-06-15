"""
📥 文档注入 v0.4.5 — 两阶段智能摄入管线 + 多格式支持

阶段一：内容准备（三个 Tab：上传/OCR/手动）+ 文件类型自动检测
阶段二：元数据标注（LLM 自动分类 + 文件元数据 + 人工确认）→ 摄入
"""

import streamlit as st
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import kb_query
from config import classifications
from utils.ui_utils import (
    render_sidebar, cached_stats, cached_collections, save_env, clear_kb_caches,
)
from utils.flame_bg import render_flame_banner
from utils.ingest_ui import render_facet_form, build_facet_metadata
from utils.file_handler import (
    detect_file_type, extract_text, extract_auto_metadata, detect_encoding,
    SIZE_LIMIT_MB, FORMAT_DISPLAY_NAMES,
)

# Streamlit 支持的文件类型（扩展名无点）
STREAMLIT_FILE_TYPES = [
    "txt", "md", "json", "csv",
    "pdf", "epub", "html", "htm",
    "srt", "docx", "pptx",
    "png", "jpg", "jpeg", "bmp", "webp", "tiff",
]

# ═══════════════════════
# Session state 初始化
# ═══════════════════════
st.session_state.setdefault("ingest_content", "")
st.session_state.setdefault("ingest_source", "")
st.session_state.setdefault("ingest_method", "")
st.session_state.setdefault("classify_result", None)
st.session_state.setdefault("auto_metadata", None)    # 文件自带元数据
st.session_state.setdefault("file_info", None)        # 文件类型检测结果
st.session_state.setdefault("ingest_stage", "input")  # input → classify → done

# ═══════════════════════
# 侧边栏 + 标题
# ═══════════════════════
with st.sidebar:
    render_sidebar()

st.title("📥 文档注入")
render_flame_banner()

collection = st.session_state.get("active_collection", kb_query.DEFAULT_COLLECTION)
st.markdown(f"向 **{collection}** 知识库中摄入文档。")
st.caption(f"📂 文件目录: {st.session_state.kb_root_path}")

qdrant_info = cached_stats(collection)
if qdrant_info.get("status") != "ok":
    st.error("⚠️ Qdrant 向量数据库未运行，无法摄入。请先启动 `run.bat`。")

# ═══════════════════════════════════════════
# 阶段一：内容准备（三个 Tab）
# ═══════════════════════════════════════════
if st.session_state.ingest_stage == "input":
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["📄 上传文件", "🖼️ OCR 图片", "✏️ 手动输入"])

    # ── Tab 1: 上传文件 ──
    with tab1:
        st.markdown("#### 上传文件")
        st.caption(
            "支持 8 种核心格式：EPUB / PDF / TXT / MD / HTML / "
            "SRT 字幕 / DOCX / PPTX / JSON / CSV / 图片（JPG/PNG 等）"
        )

        uploaded_file = st.file_uploader(
            "选择文件", type=STREAMLIT_FILE_TYPES,
            help="上传后自动检测文件类型并提取内容。支持编码自动检测（UTF-8/GBK）。",
        )

        if uploaded_file is not None:
            # 文件大小检查
            file_size_mb = len(uploaded_file.getvalue()) / 1024 / 1024
            if file_size_mb > SIZE_LIMIT_MB:
                st.warning(
                    f"⚠️ 文件较大（{file_size_mb:.1f} MB），"
                    f"建议控制在 {SIZE_LIMIT_MB} MB 以内。"
                    f"处理可能需要较长时间。"
                )

            # 保存文件
            save_path = os.path.join(st.session_state.kb_root_path, uploaded_file.name)
            os.makedirs(os.path.dirname(save_path) or st.session_state.kb_root_path, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"✅ 文件已保存：{uploaded_file.name}")

            # ── 文件类型检测 ──
            file_info = detect_file_type(save_path)
            st.session_state.file_info = file_info

            # 显示检测结果 Banner
            tier = file_info.get("tier")
            tier_emoji = {1: "📚", 2: "📄", 3: "🖼️", "auto": "🔍"}.get(tier, "📁")
            auto_meta_badge = " 📎 自带元数据" if file_info.get("has_auto_metadata") else ""
            st.info(
                f"{tier_emoji} **{file_info.get('display_name', '未知')}** | "
                f"层级 {tier} · {file_info.get('tier_name', '')}{auto_meta_badge}"
            )
            if file_info.get("warning"):
                st.warning(file_info["warning"])
            if file_info.get("error"):
                st.error(file_info["error"])

            # ── 文本提取 ──
            if tier == 3:
                # 图片格式：引导到 OCR Tab
                st.info("🖼️ 这是图片文件，请切换到 **「OCR 图片」** 标签页进行识别。")
                raw_text = ""
            elif file_info["format"] in ("docx", "pptx"):
                # DOCX/PPTX 需要特殊提取
                extract_result = extract_text(save_path, file_info)
                if extract_result["ok"]:
                    raw_text = extract_result["text"]
                    with st.expander("📄 文本预览"):
                        preview = raw_text[:5000] if raw_text else "（文本为空）"
                        st.code(preview, language=None)
                    if len(raw_text) > 5000:
                        st.caption(f"... 全文共 {len(raw_text)} 字符")
                else:
                    st.warning(f"⚠️ {extract_result.get('error', '文本提取失败')}")
                    raw_text = ""
            elif file_info["format"] == "epub":
                # EPUB: 提取文本 + 元数据
                with st.spinner("正在解析 EPUB..."):
                    extract_result = extract_text(save_path, file_info)
                if extract_result["ok"]:
                    raw_text = extract_result["text"]
                    with st.expander("📄 文本预览"):
                        preview = raw_text[:5000] if raw_text else "（文本为空）"
                        st.code(preview, language=None)
                    if len(raw_text) > 5000:
                        st.caption(f"... 全文共 {len(raw_text)} 字符")
                else:
                    st.warning(f"⚠️ {extract_result.get('error', 'EPUB 解析失败')}")
                    raw_text = ""
            elif file_info["format"] == "pdf":
                # PDF: 双路径提取
                with st.spinner("正在提取 PDF 文本..."):
                    extract_result = extract_text(save_path, file_info)
                if extract_result["ok"]:
                    raw_text = extract_result["text"]
                    if extract_result.get("warning"):
                        st.warning(extract_result["warning"])
                    if extract_result.get("ocr_recommended"):
                        st.info("💡 建议切换到「OCR 图片」标签页，对扫描版 PDF 进行 OCR 识别。")
                        raw_text = raw_text or ""
                    with st.expander("📄 文本预览"):
                        preview = raw_text[:5000] if raw_text else "（未检测到文字层，可能是扫描版）"
                        st.code(preview, language=None)
                    if len(raw_text) > 5000:
                        st.caption(f"... 全文共 {len(raw_text)} 字符 · 共 {extract_result.get('total_pages', '?')} 页")
                else:
                    st.warning(f"⚠️ {extract_result.get('error', 'PDF 解析失败')}")
                    raw_text = ""
            else:
                # 纯文本格式：编码检测 + 直接解码
                detected_enc = detect_encoding(save_path)
                try:
                    with open(save_path, "r", encoding=detected_enc, errors="replace") as f:
                        raw_text = f.read()
                except Exception:
                    raw_text = uploaded_file.getvalue().decode("utf-8", errors="replace")

                encoding_note = f" (编码: {detected_enc})" if detected_enc != "utf-8" else ""
                with st.expander(f"📄 文本预览{encoding_note}"):
                    st.code(raw_text[:5000], language=None)
                if len(raw_text) > 5000:
                    st.caption(f"... 全文共 {len(raw_text)} 字符")

            # ── 自动元数据提取（层级1文件）──
            if file_info.get("has_auto_metadata"):
                with st.spinner("正在提取文件元数据..."):
                    auto_meta = extract_auto_metadata(save_path, file_info)
                if auto_meta["ok"] and auto_meta["source_count"] > 0:
                    st.session_state.auto_metadata = auto_meta["flat"]
                    st.success(
                        f"📎 已从文件中自动提取 {auto_meta['source_count']} 个元数据字段："
                    )
                    meta_lines = []
                    for k, v in auto_meta["flat"].items():
                        val_preview = str(v)[:60]
                        meta_lines.append(f"• **{k}**: {val_preview}")
                    st.caption("  \n".join(meta_lines))
                else:
                    st.session_state.auto_metadata = None
            else:
                st.session_state.auto_metadata = None

            # ── 编辑区 ──
            st.markdown("---")
            edit_text = st.text_area(
                "📝 检查并编辑文本（可选）",
                value=st.session_state.get("upload_edit", raw_text),
                height=300,
                placeholder="确认文本内容无误后点击下方按钮进入阶段二...",
                key="upload_edit_area",
            )

            if st.button("✅ 确认内容，进入元数据标注", type="primary", key="upload_confirm"):
                if not edit_text.strip():
                    st.warning("⚠️ 文本内容为空")
                else:
                    st.session_state.ingest_content = edit_text.strip()
                    st.session_state.ingest_source = uploaded_file.name
                    st.session_state.ingest_method = "upload"
                    st.session_state.ingest_stage = "classify"
                    st.session_state.classify_result = None
                    st.session_state.auto_metadata = st.session_state.get("auto_metadata")
                    st.rerun()

    # ── Tab 2: OCR 图片 ──
    with tab2:
        st.markdown("#### OCR 图片识别")
        st.markdown("上传图片，自动识别文字")

        uploaded_image = st.file_uploader(
            "选择图片", type=["png", "jpg", "jpeg", "bmp"],
            help="支持 PaddleOCR 识别", key="ocr_uploader",
        )

        if uploaded_image is not None:
            img_path = os.path.join(st.session_state.kb_root_path, uploaded_image.name)
            os.makedirs(os.path.dirname(img_path), exist_ok=True)
            with open(img_path, "wb") as f:
                f.write(uploaded_image.getbuffer())
            st.image(img_path, caption="预览", width=300)

            if st.button("🔍 开始 OCR", type="primary"):
                progress_bar = st.progress(0, "正在 OCR 识别...")
                try:
                    ocr_result = kb_query._ocr_paddle(img_path)
                    progress_bar.progress(40, "OCR 完成，正在处理...")

                    if ocr_result.get("ok"):
                        text = ocr_result.get("text", "")
                        # LLM 纠错（如果配置了 API）
                        edited_text = text
                        if os.environ.get("KB_LLM_API_KEY") and text.strip():
                            try:
                                optimized = kb_query._call_llm_api(
                                    [{"role": "user", "content": f"请优化以下OCR识别结果，修正错别字，保持原意不变，直接输出优化后的文本：\n\n{text[:5000]}"}],
                                )
                                if optimized.strip():
                                    edited_text = optimized
                                    st.caption("✅ 已用 LLM 优化识别结果")
                            except Exception:
                                pass

                        st.markdown("#### 识别结果：")
                        st.text_area("OCR 输出", text, height=150, disabled=True, key="ocr_raw_output")
                        st.caption(f"置信度: {ocr_result.get('conf', 'N/A')} | 字符数: {ocr_result.get('chars', 0)}")

                        # 编辑区
                        st.session_state["ocr_edited"] = edited_text
                        final_text = st.text_area(
                            "📝 编辑确认（可修改）",
                            value=edited_text,
                            height=200,
                            key="ocr_edit_area",
                        )

                        progress_bar.progress(50, "OCR 完成")

                        if st.button("✅ 确认内容，进入元数据标注", type="primary", key="ocr_confirm"):
                            if not final_text.strip():
                                st.warning("⚠️ 识别结果为空")
                            else:
                                st.session_state.ingest_content = final_text.strip()
                                st.session_state.ingest_source = uploaded_image.name
                                st.session_state.ingest_method = "ocr"
                                st.session_state.ingest_stage = "classify"
                                st.session_state.classify_result = None
                                st.rerun()
                    else:
                        progress_bar.empty()
                        st.error(f"OCR 失败: {ocr_result.get('error', '未知错误')}")
                except Exception as e:
                    progress_bar.empty()
                    st.error(f"OCR 出错: {e}")

    # ── Tab 3: 手动输入 ──
    with tab3:
        st.markdown("#### 手动输入文本")
        st.markdown("直接粘贴文本内容")

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

        if st.button("✅ 确认内容，进入元数据标注", type="primary", key="manual_confirm"):
            if not manual_text.strip():
                st.warning("⚠️ 请输入文本内容")
            else:
                st.session_state.ingest_content = manual_text.strip()
                st.session_state.ingest_source = source_name or "手动输入"
                st.session_state.ingest_method = "manual"
                st.session_state.ingest_stage = "classify"
                st.session_state.classify_result = None
                st.rerun()

# ═══════════════════════════════════════════
# 阶段二：元数据标注 + 摄入
# ═══════════════════════════════════════════
if st.session_state.ingest_stage in ("classify", "done"):
    st.markdown("---")
    st.markdown("### 🏷️ 元数据标注")
    source = st.session_state.ingest_source
    content_len = len(st.session_state.ingest_content)
    auto_meta = st.session_state.get("auto_metadata")
    file_info = st.session_state.get("file_info")

    # 来源信息行
    info_cols = st.columns(3)
    with info_cols[0]:
        st.caption(f"📂 来源: {source}")
    with info_cols[1]:
        st.caption(f"📏 字数: {content_len}")
    with info_cols[2]:
        if auto_meta and isinstance(auto_meta, dict) and len(auto_meta) > 0:
            st.caption(f"📎 文件元数据: {len(auto_meta)} 字段已自动填充")

    # ── 文件自带元数据展示 ──
    if auto_meta and isinstance(auto_meta, dict) and len(auto_meta) > 0:
        with st.expander(f"📎 文件自带元数据（{len(auto_meta)} 字段）", expanded=False):
            meta_cols = st.columns(min(len(auto_meta), 4))
            for i, (key, val) in enumerate(auto_meta.items()):
                col = meta_cols[i % len(meta_cols)]
                val_str = str(val)[:80]
                col.metric(
                    label=key,
                    value=val_str,
                    delta="来自文件",
                    delta_color="off",
                )

    # 内容预览（折叠）
    with st.expander("📄 内容预览", expanded=False):
        st.code(st.session_state.ingest_content[:3000], language=None)
        if content_len > 3000:
            st.caption(f"... 全文共 {content_len} 字符")
        if content_len > 5000:
            st.info(
                f"💡 内容较长（{content_len} 字），AI 仅分析前 5000 字进行自动分类，"
                f"标签可能不完全准确。建议人工检查。"
            )

    # ── 自动分析按钮 ──
    st.markdown("---")
    auto_col1, auto_col2 = st.columns([2, 1])
    with auto_col1:
        st.markdown("#### 🤖 AI 自动分类")
        st.caption("LLM 读取文本内容，自动推断分面字段。建议先运行此功能再微调。")

    with auto_col2:
        llm_available = bool(os.environ.get("KB_LLM_API_KEY"))
        if not llm_available:
            st.info("💡 需配置 LLM API Key（引擎配置页）")

    if st.button("🔍 自动分析", type="secondary", disabled=not llm_available, use_container_width=True):
        with st.spinner("AI 正在分析文本内容..."):
            classify_r = kb_query.auto_classify(st.session_state.ingest_content)
            if classify_r.get("ok"):
                st.session_state.classify_result = classify_r["classification"]
                st.toast("✅ AI 分析完成！请检查并微调。", icon="🤖")
                st.rerun()
            else:
                st.error(f"自动分析失败: {classify_r.get('error', '未知错误')}")
                st.info("你可以手动填写下方表单，不影响摄入。")

    # ── 显示 LLM 分析结果 ──
    cr = st.session_state.classify_result
    if cr:
        st.markdown("---")
        st.markdown("##### 📊 AI 分析结果（已填充到表单）")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("内容类型", dict(classifications.CONTENT_TYPE_OPTIONS).get(cr.get("content_type", ""), cr.get("content_type", "—")))
        with c2:
            domains = cr.get("domain", [])
            st.metric("主题域", ", ".join(domains) if domains else "—")
        with c3:
            st.metric("可信度", f"⭐ {cr.get('trust_score', 3)}")
        with c4:
            st.metric("生命周期", dict(classifications.LIFECYCLE_OPTIONS).get(cr.get("lifecycle", ""), "—"))
        with c5:
            kws = cr.get("keywords", [])
            st.metric("关键词", ", ".join(kws[:5]) if kws else "—")

        if cr.get("title"):
            st.caption(f"📌 推断标题: {cr.get('title', '')}")
        if cr.get("author"):
            st.caption(f"✍️ 推断作者: {cr.get('author', '')}")

        st.caption("⬇️ 下方表单已自动填充，你可以修改任何字段")

    # ── 分面字段表单 ──
    st.markdown("---")

    # 准备 defaults（优先级：LLM 结果 > 文件元数据 > 默认值）
    form_defaults = {}
    if cr:
        form_defaults = {
            "content_type": cr.get("content_type"),
            "domain": cr.get("domain", []),
            "lifecycle": cr.get("lifecycle"),
            "trust_score": cr.get("trust_score"),
            "title": cr.get("title", ""),
            "author": cr.get("author", ""),
            "keywords": cr.get("keywords", []),
            "knowledge_type": cr.get("knowledge_type", ""),
        }
    # 文件自带元数据兜底（LLM 未填充的字段）
    if auto_meta and isinstance(auto_meta, dict):
        for key in ("title", "author"):
            if not form_defaults.get(key) and auto_meta.get(key):
                form_defaults[key] = auto_meta[key]
    # 手动输入默认值
    if st.session_state.ingest_method == "manual" and not cr:
        form_defaults["is_personal"] = True
        form_defaults["content_type"] = "idea"

    form_values = render_facet_form(st.session_state.ingest_method, defaults=form_defaults)

    # ── 摄入按钮 ──
    st.markdown("---")
    ingest_btn_label = f"🚀 摄入到 {collection}"
    if st.button(ingest_btn_label, type="primary", use_container_width=True):
        if qdrant_info.get("status") != "ok":
            st.error("⚠️ Qdrant 未运行，请先启动 Qdrant。")
        else:
            progress_bar = st.progress(0, "正在分块...")
            time.sleep(0.2)
            progress_bar.progress(30, "正在嵌入向量...")

            metadata = build_facet_metadata(
                form_values,
                ingest_method=st.session_state.ingest_method,
                source=st.session_state.ingest_source,
            )

            result = kb_query.ingest(
                text=st.session_state.ingest_content,
                metadata=metadata,
                collection=collection,
            )

            if result.get("ok"):
                progress_bar.progress(100, "摄入完成！")
                st.success(f"✅ 摄入成功！共 {result.get('chunks', '?')} 个分块 | 文档ID: {result.get('doc_id', '?')}")
                clear_kb_caches()
                # 重置状态
                st.session_state.ingest_content = ""
                st.session_state.ingest_source = ""
                st.session_state.ingest_method = ""
                st.session_state.classify_result = None
                st.session_state.ingest_stage = "done"
            else:
                progress_bar.empty()
                error_msg = result.get("error", "未知错误")
                if "重复" in error_msg:
                    st.warning(f"⚠️ {error_msg}")
                else:
                    st.error(f"❌ 摄入失败: {error_msg}")

    # ── 返回按钮 ──
    if st.session_state.ingest_stage == "done":
        if st.button("↩️ 继续摄入下一篇", type="secondary"):
            st.session_state.ingest_stage = "input"
            st.session_state.ingest_content = ""
            st.session_state.ingest_source = ""
            st.session_state.ingest_method = ""
            st.session_state.classify_result = None
            st.session_state.auto_metadata = None
            st.session_state.file_info = None
            st.rerun()
    else:
        if st.button("↩️ 返回重新选择内容", type="secondary"):
            st.session_state.ingest_stage = "input"
            st.session_state.ingest_content = ""
            st.session_state.ingest_source = ""
            st.session_state.ingest_method = ""
            st.session_state.classify_result = None
            st.session_state.auto_metadata = None
            st.session_state.file_info = None
            st.rerun()
