"""
KnowledgeForge / 知炬 — Streamlit Web UI 主入口
Phase 1: Streamlit 原型
"""

import streamlit as st
import os
import sys

# ============================================================
# 页面配置（必须放在最前面）
# ============================================================
st.set_page_config(
    page_title="KnowledgeForge / 知炬",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 自定义 CSS — 深色主题 + 橙红渐变强调色
# ============================================================
CUSTOM_CSS = """
<style>
    /* 全局背景 */
    .stApp {
        background-color: #0E1117;
    }
    
    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
        border-right: 1px solid #333;
    }
    
    /* 标题 */
    h1, h2, h3 {
        color: #F7C948 !important;
    }
    
    /* 按钮 — 主按钮橙红渐变 */
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #FF6B35 0%, #F7C948 100%) !important;
        color: #0E1117 !important;
        font-weight: bold !important;
        border: none !important;
        border-radius: 8px !important;
    }
    
    /* 按钮 — 次按钮 */
    .stButton > button[kind="secondary"] {
        background: #1a1a2e !important;
        color: #F7C948 !important;
        border: 1px solid #FF6B35 !important;
        border-radius: 8px !important;
    }
    
    /* 输入框 */
    .stTextInput > div > div > input {
        background-color: #1a1a2e !important;
        color: #FFFFFF !important;
        border: 1px solid #333 !important;
        border-radius: 8px !important;
    }
    
    /* 文件上传器 */
    [data-testid="stFileUploader"] {
        background: #1a1a2e;
        border: 2px dashed #FF6B35;
        border-radius: 12px;
        padding: 20px;
    }
    
    /* 成功消息 */
    .stSuccess {
        background: #1a1a2e !important;
        border-left: 4px solid #00CC66 !important;
    }
    
    /* 警告消息 */
    .stWarning {
        background: #1a1a2e !important;
        border-left: 4px solid #FF6B35 !important;
    }
    
    /* 错误消息 */
    .stError {
        background: #1a1a2e !important;
        border-left: 4px solid #FF3366 !important;
    }
    
    /* 分割线 */
    hr {
        border-color: #333 !important;
    }
    
    /* 卡片效果 */
    .css-1r6slb0 {
        background: #1a1a2e;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #333;
    }
    
    /* 侧边栏导航按钮 */
    .stSidebar .stButton > button {
        width: 100%;
        text-align: left;
        background: transparent;
        color: #FFFFFF;
        border: none;
        padding: 10px 15px;
        border-radius: 8px;
    }
    .stSidebar .stButton > button:hover {
        background: #FF6B35 !important;
        color: #0E1117 !important;
    }
    
    /* 进度条 */
    .stProgress > div > div {
        background: linear-gradient(90deg, #FF6B35 0%, #F7C948 100%) !important;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============================================================
# 侧边栏导航
# ============================================================
with st.sidebar:
    st.markdown("## 🔥 KnowledgeForge")
    st.markdown("### 知炬")
    st.markdown("---")
    
    # 导航按钮
    page = st.radio(
        "导航",
        ["📥 摄入管理", "💬 问答界面", "🗂️ 知识库管理", "⚙️ 设置"],
        label_visibility="collapsed",
    )
    
    st.markdown("---")
    st.markdown("### 📊 快速统计")
    
    # 尝试读取统计信息
    try:
        local_data_dir = "local_data"
        if os.path.exists(local_data_dir):
            files = [f for f in os.listdir(local_data_dir) if f.endswith(".json")]
            st.metric("已摄入文档", len(files))
        else:
            st.metric("已摄入文档", 0)
    except:
        st.metric("已摄入文档", "?")
    
    st.markdown("---")
    st.markdown("🔗 [GitHub](https://github.com/shiyao222333-afk/knowledge-forge)")
    st.markdown("📖 [文档](https://github.com/shiyao222333-afk/knowledge-forge/blob/main/README.md)")

# ============================================================
# 页面路由
# ============================================================
if page == "📥 摄入管理":
    st.title("📥 摄入管理")
    st.markdown("把你的知识丢进来，让 AI 帮你记住。")
    
    tab1, tab2, tab3 = st.tabs(["📄 上传文件", "🖼️ OCR 图片", "✏️ 手动输入"])
    
    with tab1:
        st.markdown("#### 上传文件")
        st.markdown("支持 .txt .pdf .md 文件")
        
        uploaded_file = st.file_uploader(
            "选择文件",
            type=["txt", "pdf", "md", "json"],
            help="上传后自动摄入到知识库"
        )
        
        if uploaded_file is not None:
            # 保存文件
            save_path = os.path.join("local_data", uploaded_file.name)
            os.makedirs("local_data", exist_ok=True)
            
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            st.success(f"✅ 文件已保存：{uploaded_file.name}")
            
            if st.button("🚀 开始摄入", type="primary"):
                with st.spinner("正在摄入..."):
                    # 调用 kb_query.py --ingest
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, "kb_query.py", "--ingest", save_path],
                        capture_output=True,
                        text=True,
                    )
                    
                    if result.returncode == 0:
                        st.success("✅ 摄入成功！")
                        st.code(result.stdout)
                    else:
                        st.error("❌ 摄入失败")
                        st.code(result.stderr)
    
    with tab2:
        st.markdown("#### OCR 图片识别")
        st.markdown("上传图片，自动识别文字并摄入")
        
        uploaded_image = st.file_uploader(
            "选择图片",
            type=["png", "jpg", "jpeg", "bmp"],
            help="支持 PaddleOCR 识别"
        )
        
        llm_optimize = st.checkbox("🧠 LLM 优化识别结果（自动修复错别字）", value=True)
        
        if uploaded_image is not None:
            # 保存图片
            img_path = os.path.join("local_data", uploaded_image.name)
            os.makedirs("local_data", exist_ok=True)
            
            with open(img_path, "wb") as f:
                f.write(uploaded_image.getbuffer())
            
            st.image(img_path, caption="预览", width=300)
            
            if st.button("🔍 开始 OCR", type="primary"):
                with st.spinner("正在识别..."):
                    # 调用 kb_query.py --ocr
                    import subprocess
                    
                    cmd = [sys.executable, "kb_query.py", "--ocr", img_path]
                    if llm_optimize:
                        cmd.append("--llm-optimize")
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                    )
                    
                    if result.returncode == 0:
                        st.success("✅ OCR 完成！")
                        st.markdown("#### 识别结果：")
                        st.code(result.stdout)
                    else:
                        st.error("❌ OCR 失败")
                        st.code(result.stderr)
    
    with tab3:
        st.markdown("#### 手动输入文本")
        st.markdown("直接粘贴文本内容，手动摄入")
        
        manual_text = st.text_area(
            "输入文本内容",
            height=300,
            placeholder="把你的笔记、想法、资料粘贴到这里..."
        )
        
        source_name = st.text_input(
            "来源标识（可选）",
            placeholder="例如：我的笔记、齿轮手册P23"
        )
        
        if st.button("💾 保存到知识库", type="primary"):
            if manual_text.strip():
                # 保存为临时文件
                import tempfile
                with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt", encoding="utf-8") as f:
                    f.write(manual_text)
                    temp_path = f.name
                
                with st.spinner("正在摄入..."):
                    import subprocess
                    cmd = [sys.executable, "kb_query.py", "--ingest", temp_path]
                    if source_name:
                        cmd.extend(["--source", source_name])
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                    )
                    
                    if result.returncode == 0:
                        st.success("✅ 保存成功！")
                        st.code(result.stdout)
                    else:
                        st.error("❌ 保存失败")
                        st.code(result.stderr)
                
                os.unlink(temp_path)
            else:
                st.warning("⚠️ 请输入文本内容")
    
elif page == "💬 问答界面":
    st.title("💬 问答界面")
    st.markdown("问一个问题，AI 会从你的知识库里找答案，并标注来源。")
    
    # 输入框
    query = st.text_input(
        "输入你的问题",
        placeholder="例如：模数 2.5 的齿轮外径是多少？",
        label_visibility="collapsed",
    )
    
    col1, col2 = st.columns([1, 5])
    with col1:
        ask_button = st.button("🚀 提问", type="primary", use_container_width=True)
    with col2:
        llm_api_key = st.text_input(
            "LLM API Key",
            type="password",
            value=os.environ.get("KB_LLM_API_KEY", ""),
            label_visibility="collapsed",
        )
    
    if ask_button and query:
        with st.spinner("正在思考..."):
            import subprocess
            
            cmd = [sys.executable, "kb_query.py", query, "--answer"]
            if llm_api_key:
                cmd.extend(["--llm-api-key", llm_api_key])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                st.success("✅ 回答生成成功！")
                
                # 尝试读取 HTML 报告
                html_path = "query_result.html"
                if os.path.exists(html_path):
                    with open(html_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    
                    st.markdown("#### 📊 回答预览：")
                    st.components.v1.html(html_content, height=600, scrolling=True)
                    
                    st.markdown("---")
                    st.markdown(f"📄 完整报告已保存到：`{html_path}`")
                    
                    # 提供下载链接
                    with open(html_path, "rb") as f:
                        st.download_button(
                            "📥 下载 HTML 报告",
                            f,
                            file_name="query_result.html",
                            mime="text/html",
                        )
            else:
                st.error("❌ 生成回答失败")
                st.code(result.stderr)
    
    elif ask_button and not query:
        st.warning("⚠️ 请输入问题")
    
elif page == "🗂️ 知识库管理":
    st.title("🗂️ 知识库管理")
    st.markdown("查看、管理已摄入的文档。")
    
    # 显示已摄入文档
    local_data_dir = "local_data"
    
    if os.path.exists(local_data_dir):
        files = [f for f in os.listdir(local_data_dir) if f.endswith(".json")]
        
        if files:
            st.markdown(f"#### 已摄入文档（共 {len(files)} 个）")
            
            for file in files:
                file_path = os.path.join(local_data_dir, file)
                
                with st.expander(file):
                    # 读取文件信息
                    try:
                        import json
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        st.markdown(f"**来源**：{data.get('source', '未知')}")
                        st.markdown(f"**时间**：{data.get('timestamp', '未知')}")
                        st.markdown(f"**内容预览**：")
                        st.text(data.get('text', '')[:200] + "...")
                        
                        if st.button("🗑️ 删除", key=f"del_{file}"):
                            os.remove(file_path)
                            st.success(f"✅ 已删除：{file}")
                            st.rerun()
                    except Exception as e:
                        st.error(f"读取失败：{e}")
        else:
            st.info("📭 知识库为空，请先摄入文档。")
    else:
        st.info("📭 知识库为空，请先摄入文档。")
    
elif page == "⚙️ 设置":
    st.title("⚙️ 设置")
    st.markdown("配置 LLM 和系统参数。")
    
    with st.form("settings_form"):
        st.markdown("#### LLM 配置")
        
        llm_api_key = st.text_input(
            "LLM API Key",
            value=os.environ.get("KB_LLM_API_KEY", ""),
            type="password",
            help="DeepSeek / Qwen 等兼容 OpenAI API 的密钥"
        )
        
        llm_base_url = st.text_input(
            "LLM API 地址",
            value=os.environ.get("KB_LLM_BASE_URL", "https://api.deepseek.com/v1"),
            help="默认：DeepSeek API 地址"
        )
        
        llm_model = st.text_input(
            "LLM 模型名称",
            value=os.environ.get("KB_LLM_MODEL", "deepseek-chat"),
            help="默认：deepseek-chat"
        )
        
        st.markdown("#### 系统参数")
        
        table_split_threshold = st.slider(
            "表格拆分阈值（行数 > 此值时拆分）",
            min_value=2,
            max_value=10,
            value=4,
            help="大表格按行拆分，提高引用精度"
        )
        
        submitted = st.form_submit_button("💾 保存设置")
        
        if submitted:
            # 保存到环境变量（会话级别）
            os.environ["KB_LLM_API_KEY"] = llm_api_key
            os.environ["KB_LLM_BASE_URL"] = llm_base_url
            os.environ["KB_LLM_MODEL"] = llm_model
            
            st.success("✅ 设置已保存（本次会话有效）")
            st.info("💡 要永久保存，请设置系统环境变量，或创建 `.env` 文件")
