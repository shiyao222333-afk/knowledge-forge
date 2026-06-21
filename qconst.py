"""
Citrinitas · 熔知 — 共享常量

被 doc_manager / qdrant_client / kb_query 等模块共同引用。
避免循环导入，内容保持最小化。
"""

import os
import requests

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
QDRANT_URL = os.environ.get("KB_QDRANT_URL", "http://127.0.0.1:6333")
DEFAULT_COLLECTION = "athanor_v1"
IMAGES_DIR = os.path.join(PROJECT_DIR, "local_data", "images")
INGEST_LOG_PATH = os.path.join(PROJECT_DIR, "local_data", "ingest_log.jsonl")


def _check_qdrant() -> bool:
    """检查 Qdrant 是否运行（纯检查，无副作用）。"""
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
