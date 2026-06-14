"""
KnowledgeForge / 知炬 — Streamlit Web UI 主入口
Phase 3: pages/ 多文件架构 + st.navigation

页面:
  文档注入 — 上传/OCR/手动输入/预览/LLM优化/编辑/写入
  智能检索 — 搜索+问答合并，勾选是否用LLM，跨库搜索
  知识中枢 — 集合仪表盘/建库向导/操作/重建迁移/导出
  引擎配置 — LLM配置/嵌入模型管理/OCR设置/系统设置
"""

import streamlit as st
import os
import sys

# ── 确保 kb_query 可导入 ──
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# ── .env 持久化 ──
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

def _load_env():
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                os.environ[key] = value

_load_env()

import kb_query

if os.environ.get("KB_EMBED_MODEL"):
    kb_query.EMBED_MODEL = os.environ["KB_EMBED_MODEL"]

# ── 页面配置 ──
st.set_page_config(
    page_title="KnowledgeForge / 知炬",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session State 初始化 ──
if "active_collection" not in st.session_state:
    st.session_state.active_collection = kb_query.DEFAULT_COLLECTION
if "kb_root_path" not in st.session_state:
    st.session_state.kb_root_path = os.environ.get("KB_ROOT_PATH") or os.path.join(
        PROJECT_DIR, "local_data"
    )
if "last_answer" not in st.session_state:
    st.session_state.last_answer = None
if "last_search" not in st.session_state:
    st.session_state.last_search = None
if "fetched_llm_models" not in st.session_state:
    st.session_state.fetched_llm_models = []

# ── CSS 加载 ──
@st.cache_resource(show_spinner=False)
def _load_css() -> str:
    css_path = os.path.join(PROJECT_DIR, "assets", "style.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            return f"<style>\n{f.read()}\n</style>"
    except FileNotFoundError:
        return ""

st.markdown(_load_css(), unsafe_allow_html=True)

# ── 页面注册 ──
pages = [
    st.Page("pages/0_📹_关于.py", title="关于", icon="📹"),
    st.Page("pages/1_文档注入.py", title="文档注入", icon="📥"),
    st.Page("pages/2_智能检索.py", title="智能检索", icon="💬"),
    st.Page("pages/3_知识中枢.py", title="知识中枢", icon="🗂️"),
    st.Page("pages/4_引擎配置.py", title="引擎配置", icon="⚙️"),
]

pg = st.navigation(pages)
pg.run()
