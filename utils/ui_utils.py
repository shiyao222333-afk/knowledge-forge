"""
共享 UI 组件 — 侧边栏系统状态、知识库选择器、缓存函数
被 pages/ 下的所有页面复用
"""

import streamlit as st
import os
import requests

# ── 确保 kb_query 可导入 ──
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import kb_query

# ═══════════════════════════════════════════
# 缓存
# ═══════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def cached_collections() -> dict:
    if not cached_qdrant_online():
        return {"ok": False, "collections": []}
    return kb_query.list_collections()

@st.cache_data(ttl=600, show_spinner=False)
def cached_qdrant_online() -> bool:
    try:
        resp = requests.get(f"{kb_query.QDRANT_URL}/collections", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False

@st.cache_data(ttl=300, show_spinner=False)
def cached_stats(collection: str = None) -> dict:
    if collection is None:
        collection = st.session_state.get("active_collection", kb_query.DEFAULT_COLLECTION)
    try:
        resp = requests.get(
            f"{kb_query.QDRANT_URL}/collections/{collection}", timeout=5
        )
        if resp.status_code != 200:
            return {"status": "error", "error": f"HTTP {resp.status_code}"}
        data = resp.json()
        cfg = data.get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
        pts = data.get("result", {}).get("points_count", 0)
        return {
            "status": "ok",
            "points": pts,
            "dim": cfg.get("size", "?") if cfg else "?",
            "collection": collection,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@st.cache_data(ttl=600)
def cached_embed_models() -> list:
    return kb_query.get_embed_models()

@st.cache_data(ttl=600)
def cached_ingest_log() -> list:
    return kb_query.read_ingest_log()

# ═══════════════════════════════════════════
# 侧边栏组件
# ═══════════════════════════════════════════

def render_sidebar():
    """渲染共享侧边栏：品牌 + 知识库选择器 + 系统状态。"""
    st.markdown("## 🔥 KnowledgeForge")
    st.markdown("##### 知炬 · 知识熔炉")
    st.markdown("---")

    # ── 知识库选择器 ──
    st.markdown("### 📚 当前知识库")
    col_data = cached_collections()
    collection_names = [c["name"] for c in col_data.get("collections", [])]

    if st.session_state.active_collection not in collection_names and collection_names:
        st.session_state.active_collection = collection_names[0]
    elif not collection_names:
        st.session_state.active_collection = kb_query.DEFAULT_COLLECTION

    selected_col = st.selectbox(
        "选择知识库",
        options=collection_names if collection_names else [kb_query.DEFAULT_COLLECTION],
        index=(
            collection_names.index(st.session_state.active_collection)
            if st.session_state.active_collection in collection_names
            else 0
        ),
        label_visibility="collapsed",
        key="sidebar_collection_selector",
    )
    st.session_state.active_collection = selected_col

    st.markdown("---")

    # ── 系统状态 ──
    st.markdown("### 📊 系统状态")

    qdrant_info = cached_stats(st.session_state.active_collection)
    if qdrant_info.get("status") == "ok":
        st.markdown(f"""
        <div class="kf-stats-box">
            <span class="metric-label">向量库状态</span>
            <span style="color:#00CC66">🟢 在线</span><br/>
            <span class="metric-label">文档块数</span>
            <span class="metric-value">{qdrant_info['points']}</span><br/>
            <span class="metric-label">向量维度</span>
            <span class="metric-value">{qdrant_info['dim']}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="kf-stats-box" style="border-color:#FF3366">
            <span class="metric-label">向量库状态</span>
            <span style="color:#FF3366">🔴 离线</span><br/>
            <span style="color:#888;font-size:0.8em">请先启动 Qdrant</span>
        </div>
        """, unsafe_allow_html=True)

    # ── 本地文件统计 ──
    try:
        local_data_dir = os.path.join(PROJECT_DIR, "local_data")
        if os.path.exists(local_data_dir):
            json_files = [f for f in os.listdir(local_data_dir) if f.endswith(".json")]
            st.markdown(
                f"<span style='color:#888;font-size:0.8em'>本地记录: {len(json_files)} 条</span>",
                unsafe_allow_html=True,
            )
    except Exception:
        pass

    st.markdown("---")
    st.markdown("🔗 [GitHub](https://github.com/shiyao222333-afk/knowledge-forge)")
    st.markdown("🔥 知炬")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def clear_kb_caches():
    """清除知识库相关的缓存，比 st.cache_data.clear() 更精确。"""
    cached_collections.clear()
    cached_qdrant_online.clear()
    cached_stats.clear()
    cached_embed_models.clear()
    cached_ingest_log.clear()

def save_env(kv: dict):
    """增量写入 .env 文件。"""
    env_file = os.path.join(PROJECT_DIR, ".env")
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    for key, val in kv.items():
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0].strip() == key:
                lines[i] = f"{key}={val}\n"
                found = True
                break
        if not found:
            lines.append(f"{key}={val}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)
