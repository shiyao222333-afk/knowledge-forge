"""
⚙️ 引擎配置 — LLM 配置 / 嵌入模型管理 / OCR 设置 / 系统设置
"""

import streamlit as st
import os
import sys
import requests

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import kb_query
from utils.ui_utils import (
    render_sidebar, cached_embed_models, cached_ingest_log, save_env, clear_kb_caches,
)
from utils.flame_bg import render_flame_banner

# ── 侧边栏 ──
with st.sidebar:
    render_sidebar()

# ── 标题 ──
st.title("⚙️ 引擎配置")
render_flame_banner()
st.markdown("配置底层引擎参数。保存后写入 `.env` 文件，重启不丢失。")

# ── 嵌入模型预设 ──
EMBED_PRESETS = {
    "qwen3-embedding": "qwen3-embedding:4b",
    "bge-m3": "bge-m3:latest",
    "nomic-embed-text": "nomic-embed-text:latest",
    "mxbai-embed-large": "mxbai-embed-large:latest",
}

# ── Dialog：删除嵌入模型（定义在顶层，避免条件块 NameError）──
@st.dialog("删除嵌入模型")
def dialog_embed_delete():
    model_name = st.session_state.get("embed_del_target", "")
    st.warning(f"⚠️ 确定删除模型 **{model_name}** 吗？")
    st.caption("删除后旧的向量数据将不可用，需重建。")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ 确认", type="primary", use_container_width=True, key="confirm_embed_del"):
            import subprocess
            subprocess.run(["ollama", "rm", model_name], capture_output=True)
            clear_kb_caches()
            st.success("已删除")
            st.session_state.show_embed_del = False
            st.rerun()
    with c2:
        if st.button("❌ 取消", use_container_width=True, key="cancel_embed_del"):
            st.session_state.show_embed_del = False
            st.rerun()

# ── LLM 预设 ──
LLM_PRESETS = {
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "qwen": {"label": "通义千问 (Qwen)", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
    "zhipu": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4"},
    "moonshot": {"label": "Moonshot (Kimi)", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "custom": {"label": "🔧 自定义", "base_url": "", "model": ""},
}

if st.session_state.get("show_embed_del"):
    dialog_embed_delete()

# ═══════════════════════════════════════════
tab_llm, tab_embed, tab_sys = st.tabs(["🤖 LLM 配置", "🔤 嵌入模型", "🔧 系统设置"])

# ═══════ Tab 1: LLM 配置 ═══════
with tab_llm:
    st.markdown("#### 🤖 LLM API 配置")
    st.caption("用于 AI 问答的语言模型服务配置。")

    current_base = os.environ.get("KB_LLM_BASE_URL", "")
    detected = "custom"
    for pk, pv in LLM_PRESETS.items():
        if pk == "custom":
            continue
        if pv["base_url"] and current_base.rstrip("/") == pv["base_url"].rstrip("/"):
            detected = pk
            break

    preset_keys = list(LLM_PRESETS.keys())
    preset = st.selectbox(
        "LLM 服务商",
        options=preset_keys,
        format_func=lambda x: LLM_PRESETS[x]["label"],
        index=preset_keys.index(detected) if detected in preset_keys else preset_keys.index("custom"),
    )
    pdata = LLM_PRESETS[preset]

    llm_api_key = st.text_input(
        "API Key",
        value=os.environ.get("KB_LLM_API_KEY", ""),
        type="password",
        placeholder="sk-...",
    )
    llm_base_url = st.text_input(
        "API 地址",
        value=os.environ.get("KB_LLM_BASE_URL") or pdata["base_url"],
        help="OpenAI 兼容的 /v1 地址",
    )

    # 模型选择（支持在线获取）
    st.markdown("#### 🧠 模型选择")
    fcol1, fcol2 = st.columns([1, 3])
    with fcol1:
        fetch_btn = st.button("📡 在线获取模型", help="从 API 读取可用模型列表",
                              disabled=not llm_api_key.strip())
    with fcol2:
        if st.session_state.get("fetched_llm_models"):
            st.caption(f"✅ 已缓存 {len(st.session_state['fetched_llm_models'])} 个模型")

    if fetch_btn:
        if not llm_base_url.strip():
            st.warning("⚠️ 请先填写 API 地址")
        else:
            with st.spinner("📡 正在获取..."):
                try:
                    resp = requests.get(
                        f"{llm_base_url.rstrip('/')}/models",
                        headers={"Authorization": f"Bearer {llm_api_key.strip()}"},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        models = sorted([m.get("id", "") for m in data.get("data", []) if m.get("id")])
                        st.session_state.fetched_llm_models = models
                        st.success(f"✅ 找到 {len(models)} 个模型")
                        st.rerun()
                    else:
                        st.error(f"❌ HTTP {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    st.error(f"请求失败: {e}")

    fetched = st.session_state.get("fetched_llm_models", [])
    current_model = os.environ.get("KB_LLM_MODEL", "") or pdata["model"]

    if fetched:
        if current_model and current_model not in fetched:
            fetched = [current_model] + fetched
        model_idx = fetched.index(current_model) if current_model in fetched else 0
        llm_model = st.selectbox("模型", options=fetched, index=model_idx)
    else:
        llm_model = st.text_input("模型名称", value=current_model,
                                  placeholder=pdata["model"] or "输入模型名称...")

    if st.button("💾 保存 LLM 配置", type="primary"):
        save_env({
            "KB_LLM_API_KEY": llm_api_key,
            "KB_LLM_BASE_URL": llm_base_url,
            "KB_LLM_MODEL": llm_model,
        })
        os.environ["KB_LLM_API_KEY"] = llm_api_key
        os.environ["KB_LLM_BASE_URL"] = llm_base_url
        os.environ["KB_LLM_MODEL"] = llm_model
        st.success("✅ LLM 配置已保存！")

# ═══════ Tab 2: 嵌入模型 ═══════
with tab_embed:
    st.markdown("#### 🔤 嵌入模型管理")
    st.caption("把文档变成向量的模型。不同模型向量格式不同，换模型后需要重建。")

    current_embed = os.environ.get("KB_EMBED_MODEL", kb_query.EMBED_MODEL)

    # ── 预设区域 ──
    st.markdown("##### 📦 预设模型")
    embed_cols = st.columns(2)

    local_models = cached_embed_models()

    for i, (key, full_name) in enumerate(EMBED_PRESETS.items()):
        with embed_cols[i % 2]:
            # 检查是否已下载
            is_downloaded = any(key in m for m in local_models)
            is_current = current_embed == full_name

            status_text = "✅ 已下载" if is_downloaded else "⬇️ 未下载"
            status_color = "#00CC66" if is_downloaded else "#888"

            st.markdown(f"""
            <div style="
                background: rgba(26, 26, 46, 0.8);
                border: 1px solid {'#FF6B35' if is_current else '#333'};
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 8px;
            ">
                <span style="font-weight:500;color:#F7C948;">{key}</span>
                <span style="color:{status_color};float:right;font-size:12px;">{status_text}</span>
                <br><span style="color:#888;font-size:11px;">{full_name}</span>
            </div>
            """, unsafe_allow_html=True)

            btn_label = "✅ 使用此模型" if is_current else "🔄 切换"
            if is_downloaded:
                if st.button(btn_label, key=f"use_{key}", use_container_width=True):
                    save_env({"KB_EMBED_MODEL": full_name})
                    os.environ["KB_EMBED_MODEL"] = full_name
                    kb_query.EMBED_MODEL = full_name
                    st.success(f"✅ 已切换到 {full_name}")
                    st.rerun()
                if st.button("🗑️ 删除模型", key=f"rm_{key}", use_container_width=True, type="secondary"):
                    st.session_state.embed_del_target = full_name
                    st.session_state.show_embed_del = True
                    st.rerun()
            else:
                if st.button("⬇️ 下载", key=f"dl_{key}", use_container_width=True):
                    with st.spinner(f"正在下载 {full_name}..."):
                        try:
                            import subprocess
                            result = subprocess.run(
                                ["ollama", "pull", full_name],
                                capture_output=True, text=True, timeout=300
                            )
                            if result.returncode == 0:
                                st.success(f"✅ {full_name} 下载完成！")
                                clear_kb_caches()
                                st.rerun()
                            else:
                                st.error(f"下载失败: {result.stderr[:200]}")
                        except Exception as e:
                            st.error(f"下载失败: {e}")

    # ── 搜索/自定义 ──
    st.markdown("---")
    st.markdown("##### 🔍 搜索或自定义")

    search_col1, search_col2 = st.columns([2, 1])
    with search_col1:
        custom_model = st.text_input(
            "嵌入模型名称",
            value=current_embed,
            placeholder="输入 Ollama 模型名或自定义...",
            key="custom_embed",
        )
    with search_col2:
        if st.button("🔍 搜索模型", use_container_width=True):
            with st.spinner("搜索中..."):
                try:
                    import subprocess
                    result = subprocess.run(
                        ["ollama", "list"],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        st.success("已刷新本地模型列表")
                        clear_kb_caches()
                        st.rerun()
                    else:
                        st.warning("无法刷新")
                except Exception as e:
                    st.warning(f"搜索失败: {e}")

    if custom_model != current_embed:
        st.warning("⚠️ 本地/自定义模型可能无法正常运行。保存后需用「知识中枢」重建旧数据。")
        if st.button("💾 保存并切换", type="primary"):
            save_env({"KB_EMBED_MODEL": custom_model})
            os.environ["KB_EMBED_MODEL"] = custom_model
            kb_query.EMBED_MODEL = custom_model
            st.success(f"✅ 已切换嵌入模型到: {custom_model}")
            st.rerun()

    # ── 远程 Embedding API ──
    st.markdown("---")
    st.markdown("##### 🌐 远程 Embedding API（可选）")
    st.caption("如果不使用 Ollama 本地模型，可以配置远程嵌入服务。")

    remote_enabled = st.checkbox("启用远程 Embedding API", value=bool(os.environ.get("KB_EMBED_API_KEY")))
    if remote_enabled:
        remote_url = st.text_input("远程 API 地址",
                                   value=os.environ.get("KB_EMBED_BASE_URL", ""),
                                   placeholder="https://api.example.com/v1/embeddings")
        remote_key = st.text_input("远程 API Key",
                                   value=os.environ.get("KB_EMBED_API_KEY", ""),
                                   type="password")
        remote_model = st.text_input("远程模型名",
                                     value=os.environ.get("KB_EMBED_MODEL_NAME", "text-embedding-3-small"))
        if st.button("💾 保存远程配置", type="primary"):
            save_env({
                "KB_EMBED_BASE_URL": remote_url,
                "KB_EMBED_API_KEY": remote_key,
                "KB_EMBED_MODEL_NAME": remote_model,
            })
            st.success("✅ 远程配置已保存（当前版本优先使用本地 Ollama）")

# ═══════ Tab 3: 系统设置 ═══════
with tab_sys:
    st.markdown("#### 🔧 系统设置")

    st.markdown("##### 📂 文件路径")
    kb_root = st.text_input(
        "知识库文件根目录",
        value=st.session_state.kb_root_path,
        help="摄入文件时从此目录读取。",
    )
    qdrant_url = st.text_input(
        "Qdrant 地址",
        value=os.environ.get("KB_QDRANT_URL", kb_query.QDRANT_URL),
        help="向量数据库服务地址。",
    )

    st.markdown("---")
    st.markdown("##### 📄 临时文件管理")
    try:
        local_data = os.path.join(PROJECT_DIR, "local_data")
        if os.path.exists(local_data):
            files = [f for f in os.listdir(local_data) if os.path.isfile(os.path.join(local_data, f))]
            total_size = sum(os.path.getsize(os.path.join(local_data, f)) for f in files)
            st.markdown(f"`local_data/` 目录：{len(files)} 个文件，共 {total_size:,} 字节")
        else:
            st.caption("`local_data/` 目录不存在")
    except Exception as e:
        st.caption(f"无法读取: {e}")

    if st.button("🧹 清理缓存", type="secondary"):
        clear_kb_caches()
        st.success("✅ 缓存已刷新")
        st.rerun()

    st.markdown("---")
    st.markdown("##### ℹ️ 系统信息")
    st.json({
        "kb_query 版本": kb_query.__version__,
        "Qdrant 地址": kb_query.QDRANT_URL,
        "Ollama 地址": kb_query.OLLAMA_URL,
        "嵌入模型": kb_query.EMBED_MODEL,
        "LLM 模型": os.environ.get("KB_LLM_MODEL", kb_query.LLM_MODEL),
    })

    st.markdown("---")
    if st.button("💾 保存系统设置", type="primary", use_container_width=True):
        save_env({
            "KB_ROOT_PATH": kb_root,
            "KB_QDRANT_URL": qdrant_url,
        })
        os.environ["KB_QDRANT_URL"] = qdrant_url
        st.session_state.kb_root_path = kb_root
        st.success("✅ 系统设置已保存！")
