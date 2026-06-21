"""
KB Query Engine - 中文技术文档知识库问答系统
版本: v0.4.6 — AI分析确认卡片 + 元数据预填

架构:
  摄入: 图片/文本 → PaddleOCR/PPStructureV3 → 分块嵌入 → Qdrant
  查询: 自然语言 → 向量搜索 → LLM API合成 → 程序渲染HTML/PDF

用法:
  # 问答（端到端：搜索 → API合成 → HTML报告 → PDF）
  python kb_query.py "齿轮的失效形式有哪些" --answer
  
  # 纯搜索（不调用 LLM）
  python kb_query.py "齿轮的失效形式有哪些" --top 10
  
  # 摄入文档
  python kb_query.py --ingest "D:/Documents/KnowledgeBase/机械设计/原始文件/齿轮设计基础.txt"
  
  # OCR 图片（方案B：OCR → 质量检查 → WorkBuddy审核 → 入库）
  python kb_query.py --ocr "photo.jpg" --source "手册-P3"
  python kb_query.py --ocr "photo.jpg" --check-only          # 只识别不入库，先审核
  python kb_query.py --ocr "photo.jpg" --engine structured  # PPStructureV3 结构化识别（公式+表格+图表）

环境变量（问答模式需配置 API）:
  KB_LLM_BASE_URL    LLM API 地址（默认 https://api.deepseek.com/v1）
  KB_LLM_API_KEY      API Key（需自行申请）
  KB_LLM_MODEL        模型名（默认 deepseek-chat）
"""
import requests
import json
import sys
import os
import argparse
import re
import subprocess
import io
import base64
import math
from typing import Optional
from collections import defaultdict
import hashlib
import uuid
from datetime import datetime, timezone
import tempfile
from docx import Document
from bs4 import BeautifulSoup
from config.classifications import normalize_facet_values, CLASSIFY_RULES

from qconst import (
    PROJECT_DIR, QDRANT_URL, DEFAULT_COLLECTION,
    IMAGES_DIR, INGEST_LOG_PATH, _check_qdrant,
    OLLAMA_URL, EMBED_MODEL, EMBED_DIM,
)
from doc_manager import (
    _log_ingest, read_ingest_log,
    list_documents, get_document, delete_document, update_document,
    update_metadata, set_doc_relations, search_by_doc_id, get_doc_ids,
)
from qdrant_client import (
    _ensure_collection, create_collection, list_collections,
    clear_collection, delete_collection, get_embed_models, has_any_data,
)
from text_pipeline import (
    _embed, _chunk_text, _text_hash, _extract_images, _ensure_images_dir,
    _detect_language, detect_language, detect_encoding,
    extract_text, ocr_image,
)

__version__ = "0.7.0-dev"

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except ImportError:
    FPDF = None
    XPos = None
    YPos = None

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    PILImage = None
    HAS_PIL = False

# 引用粒度：表格行数 > 此值时按行拆分为独立引用（--table-split-threshold 可覆盖）
TABLE_SPLIT_THRESHOLD = 4



# ═══════════════════════════════════════════
# 核心 API
# ═══════════════════════════════════════════

def ingest(
    file_path: str = None,
    text: str = None,
    collection: str = DEFAULT_COLLECTION,
    metadata: dict = None,
    model: str = EMBED_MODEL,
    skip_duplicates: bool = True,
    field_sources: dict = None,
    overall_confidence: float = None,
) -> dict:
    """
    摄入文档到知识库。

    参数:
        file_path: 文件路径（与 text 二选一）
        text: 文本内容（与 file_path 二选一）
        collection: Qdrant 集合名
        metadata: 自定义元数据
        model: Ollama 嵌入模型名
        skip_duplicates: 是否跳过重复内容
        field_sources: 字段来源标记 {"content_type": "rule", ...}（阶段二新增）
        overall_confidence: 程序计算的整体置信度 0.0-1.0（阶段二新增）

    返回:
        {"ok": true/false, "chunks": N, "collection": "...", "source": "..."}
    """
    if not _ensure_collection(collection):
        return {"ok": False, "error": "Qdrant 未运行。请先启动 Qdrant（双击 run.bat）。"}

    # 读取内容
    if file_path:
        if not os.path.exists(file_path):
            return {"ok": False, "error": f"文件不存在: {file_path}"}
        # 根据文件扩展名选择读取方式
        ext = os.path.splitext(file_path)[1].lower()
        text_formats = (".txt", ".md", ".json", ".csv", ".log")
        if ext in text_formats:
            # 文本格式：直接读取（自动检测编码）
            enc = detect_encoding(file_path)
            try:
                with open(file_path, "r", encoding=enc) as f:
                    text = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="latin-1") as f:
                    text = f.read()
        else:
            # 二进制格式：调用 extract_text() 提取文本
            result = extract_text(file_path)
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error", "文本提取失败")}
            text = result["text"]
        source = os.path.basename(file_path)
    elif text:
        source = metadata.get("source", "直接输入") if metadata else "直接输入"
    else:
        return {"ok": False, "error": "请提供 file_path 或 text"}
    source = source or "unknown"  # 防御性兜底

    if not text or not text.strip():
        return {"ok": False, "error": "文本内容为空"}

    # ── 去重检查 ──
    content_hash = _text_hash(text)
    if skip_duplicates:
        try:
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={
                    "filter": {
                        "must": [{"key": "content_hash", "match": {"value": content_hash}}]
                    },
                    "limit": 1
                },
                timeout=10
            )
            if resp.status_code == 200 and resp.json().get("result", {}).get("points"):
                return {
                    "ok": False,
                    "error": "内容重复，已跳过（使用 --no-dedup 强制入库）",
                    "duplicate_of": resp.json()["result"]["points"][0]["payload"].get("source", "未知"),
                    "content_hash": content_hash
                }
        except Exception:
            pass  # 去重检查失败不影响主流程

    # ── 提取图片引用并验证 ──
    _ensure_images_dir()
    image_refs = _extract_images(text)
    valid_images = []
    for img_path in image_refs:
        if os.path.isfile(img_path):
            # D5 修复：存储相对路径（提高可移植性）
            valid_images.append(os.path.relpath(os.path.abspath(img_path), PROJECT_DIR))
        elif os.path.isfile(os.path.join(IMAGES_DIR, os.path.basename(img_path))):
            # D5 修复：存储相对路径（提高可移植性）
            valid_images.append(os.path.relpath(os.path.join(IMAGES_DIR, os.path.basename(img_path)), PROJECT_DIR))

    # ── 切块 ──
    chunks = _chunk_text(text)
    if not chunks:
        return {"ok": False, "error": "切块后无内容"}

    # ── 嵌入 ──
    try:
        vectors = _embed(chunks, model=model)
    except Exception as e:
        return {"ok": False, "error": f"嵌入失败: {e}"}

    # ── 嵌入容错：至少 50% 成功才写入 ──
    if not vectors:
        return {"ok": False, "error": "所有块嵌入失败"}
    if len(vectors) < len(chunks) * 0.5:
        return {
            "ok": False,
            "error": f"嵌入成功率过低 ({len(vectors)}/{len(chunks)})，已中止"
        }
    # 对齐：vectors 可能少于 chunks（部分失败跳过），取前 N 个匹配
    if len(vectors) < len(chunks):
        print(f"  [WARN] {len(chunks) - len(vectors)}/{len(chunks)} 块嵌入失败，已跳过")
        chunks = chunks[:len(vectors)]

    # ── 构建 Qdrant points（v4.0 分组字段结构）──
    base_meta = metadata or {}
    # doc_id: 文档级唯一标识（完整 UUID，非截短）
    doc_id = base_meta.get("doc_id") or str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc).isoformat()
    full_text_hash = _text_hash(text)

    # ── 分面字段（调用 normalize_facet_values 做枚举守卫）──
    facet_raw = {
        "content_type":    base_meta.get("content_type", "knowledge"),
        "domain":          base_meta.get("domain", []),
        "temporal_nature": base_meta.get("temporal_nature", "timeboxed"),
        "epistemic_status": base_meta.get("epistemic_status", "unverified"),
    }
    facet_norm = normalize_facet_values(facet_raw)
    content_type    = facet_norm["content_type"]
    domain          = facet_norm["domain"] if isinstance(facet_norm["domain"], list) else [facet_norm["domain"]]
    temporal_nature = facet_norm["temporal_nature"]
    epistemic_status = facet_norm["epistemic_status"]

    # ── 生命周期（普通字段）──
    lifecycle      = base_meta.get("lifecycle", "published")
    project_source = base_meta.get("project_source", "")  # 降级为普通字段

    # ── 知识管理字段 ──
    knowledge_type = base_meta.get("knowledge_type", "")
    is_personal    = base_meta.get("is_personal", False)
    trust_score    = base_meta.get("trust_score", 3)
    tags           = base_meta.get("tags", [])
    is_canonical   = base_meta.get("is_canonical", True)
    relations      = base_meta.get("relations", [])
    keywords       = base_meta.get("keywords", [])
    auto_summary   = base_meta.get("auto_summary", "")

    # ── 时效性 + 版本 ──
    title          = base_meta.get("title") or source
    publish_date   = base_meta.get("publish_date", None)
    effective_date = base_meta.get("effective_date", None)
    expiry_date    = base_meta.get("expiry_date", None)
    version        = base_meta.get("version", "")

    # ── 来源元数据 ──
    author        = base_meta.get("author", "")
    source_url    = base_meta.get("source_url", "")
    file_type     = base_meta.get("file_type", "txt")
    ingest_method = base_meta.get("ingest_method", "manual")

    # ── 内容创作字段 ──
    target_platform = base_meta.get("target_platform", "none")
    related_product = base_meta.get("related_product", "")

    # ── 系统字段 ──
    language     = base_meta.get("language") or _detect_language(text)
    access_level = base_meta.get("access_level", "private")
    batch_id     = base_meta.get("batch_id", "")
    needs_review = base_meta.get("needs_review", False)  # 置信度路由标记

    # ── 阶段二新增：字段来源 + 置信度 ──
    field_sources_payload = field_sources or {}
    confidence_payload = overall_confidence if overall_confidence is not None else base_meta.get("confidence_overall", None)

    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        # 每个 chunk 用随机 64-bit ID（不依赖 Qdrant points_count，零并发冲突）
        point_id = uuid.uuid4().int >> 64
        points.append({
            "id": point_id,
            "vector": vec,
            "payload": {
                # ── 内容字段 ──
                "text": chunk,
                "title": title,
                "source": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "doc_id": doc_id,
                "doc_uid": doc_id,  # 稳定文档标识（= doc_id，未来去重键）
                "content_hash": full_text_hash,
                "images": valid_images,

                # ── 分面字段 ──
                "content_type": content_type,
                "domain": domain if isinstance(domain, list) else [domain],
                "temporal_nature": temporal_nature,
                "epistemic_status": epistemic_status,

                # ── 生命周期（普通字段）──
                "lifecycle": lifecycle,
                "project_source": project_source,
                "udc_code": base_meta.get("udc_code", ""),

                # ── 知识管理 ──
                "knowledge_type": knowledge_type,
                "is_personal": is_personal,
                "trust_score": trust_score,
                "tags": tags if isinstance(tags, list) else [],
                "is_canonical": is_canonical,
                "relations": relations if isinstance(relations, list) else [],
                "keywords": keywords if isinstance(keywords, list) else [],
                "auto_summary": auto_summary,

                # ── timeline（所有时间戳聚合）──
                "timeline": {
                    "published": publish_date,
                    "effective": effective_date,
                    "expiry": expiry_date,
                    "ingested": ingested_at,
                    "accessed": None,
                },

                # ── origin（来源追踪聚合）──
                "origin": {
                    "author": author,
                    "source_url": source_url,
                    "file_type": file_type,
                    "ingest_method": ingest_method,
                    "source_path": file_path or "",  # F8 修复：存储原始文件路径
                },

                # ── stats（使用统计聚合）──
                "stats": {
                    "access_count": 0,
                    "starred": False,
                },

                # ── 内容创作 ──
                "target_platform": target_platform,
                "related_product": related_product,
                "version": version,

                # ── 系统字段 ──
                "language": language,
                "access_level": access_level,
                "batch_id": batch_id,
                "is_archived": False,
                "needs_review": needs_review,

                # ── 阶段二新增：字段来源 + 置信度 ──
                "field_sources": field_sources_payload,
                "confidence": confidence_payload,

                # ── 预留扩展字段 ──
                "ext_text1": None, "ext_text2": None, "ext_text3": None,
                "ext_text4": None, "ext_text5": None,
                "ext_num1":  None, "ext_num2":  None, "ext_num3": None,
                "ext_bool1": None, "ext_bool2": None, "ext_bool3": None,
                "ext_date1": None, "ext_date2": None, "ext_date3": None,
            }
        })

    # 写入 Qdrant
    try:
        resp = requests.put(
            f"{QDRANT_URL}/collections/{collection}/points",
            json={"points": points},
            timeout=30
        )
        resp.raise_for_status()
    except Exception as e:
        return {"ok": False, "error": f"写入 Qdrant 失败: {e}"}

    # 写入摄入日志
    _log_ingest({
        "source_file": file_path or "",
        "source_text": text[:500] if not file_path else None,
        "collection": collection,
        "doc_id": doc_id,
        "content_hash": full_text_hash,
        "embed_model": model,
        "ingested_at": ingested_at,
    })

    return {
        "ok": True,
        "chunks": len(chunks),
        "collection": collection,
        "source": source,
        "doc_id": doc_id,
        "content_hash": full_text_hash,
        "images": valid_images
    }


def search(
    query: str,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
    score_threshold: float = 0.3,
    model: str = EMBED_MODEL,
    facet_filter: dict = None,
) -> dict:
    """
    向量搜索知识库（支持分面过滤）。

    参数:
        query: 搜索问题
        top_k: 返回结果数
        collection: 搜索的集合
        score_threshold: 最低相似度
        model: 嵌入模型
        facet_filter: 分面过滤条件，格式：
            {
                "content_type": ["knowledge"],           # 内容类型（任一匹配）
                "domain": ["0", "6"],                    # 主题域-UDC（任一匹配）
                "temporal_nature": "evergreen",          # 时效属性（单个值）
                "epistemic_status": "corroborated",      # 认知验证状态（单个值）
                "lifecycle": "published",               # 生命周期（单个值，普通字段）
                "is_personal": false,                  # 是否个人化
                "trust_score_min": 3,                  # 最低可信度
                "knowledge_type": ["formula"],          # 知识子类型
                "tags": ["齿轮"],                     # 标签（任一匹配）
            }

    返回结构:
    {
        "ok": true/false,
        "query": "原始查询",
        "total": 匹配数,
        "chunks": [{
            "text": "...", "title": "...", "source": "...",
            "score": 0.95, "chunk_index": 0, "doc_id": "...",
            "images": [...],
            # 分面字段
            "content_type": "knowledge", "domain": ["6"],
            "temporal_nature": "evergreen", "epistemic_status": "corroborated",
            # 普通字段
            "lifecycle": "published", "project_source": "",
            "udc_code": "621",
            # 知识管理
            "is_personal": false, "trust_score": 4,
            "knowledge_type": "formula", "tags": ["齿轮"],
            "is_canonical": true, "relations": [...],
            "keywords": [...], "auto_summary": "...",
            # 分组字段
            "timeline": {"published": ..., "ingested": ..., "accessed": ...},
            "origin": {"author": "...", "source_url": "...", ...},
            "stats": {"access_count": 0, "starred": false},
            # 其他
            "target_platform": "none", "version": "",
        }, ...]
    }
    """
    if not _ensure_collection(collection):
        return {"ok": False, "error": "Qdrant 未运行。请先启动 Qdrant（双击 run.bat）。"}

    # 嵌入查询
    try:
        query_vec = _embed([query], model=model)[0]
    except Exception as e:
        return {"ok": False, "error": f"嵌入查询失败: {e}"}

    # 构建过滤条件（分面过滤）
    qdrant_filter = None
    if facet_filter:
        # D7 fix: validate facet_filter keys
        _VALID_FILTER_KEYS = {"content_type","domain","knowledge_type","tags","temporal_nature","epistemic_status","lifecycle","is_personal","trust_score_min"}
        _invalid_keys = set(facet_filter.keys()) - _VALID_FILTER_KEYS
        if _invalid_keys:
            logger.warning(f"facet_filter invalid keys (ignored): {_invalid_keys}")
        must_conditions = []

        def _add_match(key, vals):
            """统一构建 match 条件（单值 or 多值 any）"""
            must_conditions.append({
                "key": key,
                "match": {"value": vals[0]} if len(vals) == 1 else {"any": vals}
            })

        # 多值匹配字段（content_type / domain / knowledge_type / tags）
        for key in ("content_type", "domain", "knowledge_type", "tags"):
            if facet_filter.get(key):
                _add_match(key, facet_filter[key])

        # 单值匹配字段（temporal_nature / epistemic_status / lifecycle）
        for key in ("temporal_nature", "epistemic_status", "lifecycle"):
            if facet_filter.get(key):
                must_conditions.append({
                    "key": key,
                    "match": {"value": facet_filter[key]}
                })

        # 布尔匹配（is_personal）
        if "is_personal" in facet_filter:
            must_conditions.append({
                "key": "is_personal",
                "match": {"value": facet_filter["is_personal"]}
            })

        # 范围匹配（trust_score_min）
        if facet_filter.get("trust_score_min") is not None:
            must_conditions.append({
                "key": "trust_score",
                "range": {"gte": facet_filter["trust_score_min"]}
            })

        if must_conditions:
            qdrant_filter = {"must": must_conditions}

    # 搜索 Qdrant
    try:
        search_body = {
            "vector": query_vec,
            "limit": top_k,
            "with_payload": True,
            "score_threshold": score_threshold
        }
        if qdrant_filter:
            search_body["filter"] = qdrant_filter

        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/search",
            json=search_body,
            timeout=30
        )
        resp.raise_for_status()
        results = resp.json()["result"]
    except Exception as e:
        return {"ok": False, "error": f"搜索失败: {e}"}

    # ── 整理结果（v4.0 分组字段）──
    chunks = []
    for r in results:
        payload = r.get("payload", {})
        chunks.append({
            "text":            payload.get("text", ""),
            "title":           payload.get("title", ""),
            "source":          payload.get("source", "未知"),
            "score":           round(r.get("score", 0), 4),
            "chunk_index":     payload.get("chunk_index", 0),
            "doc_id":          payload.get("doc_id", ""),
            "content_hash":    payload.get("content_hash", ""),
            "doc_uid":        payload.get("doc_uid", ""),
            "images":          payload.get("images", []),
            # 分面字段
            "content_type":    payload.get("content_type", "knowledge"),
            "domain":          payload.get("domain", []),
            "temporal_nature": payload.get("temporal_nature", "timeboxed"),
            "epistemic_status":payload.get("epistemic_status", "unverified"),
            # 普通字段
            "lifecycle":       payload.get("lifecycle", ""),
            "project_source":  payload.get("project_source", ""),
            "udc_code":        payload.get("udc_code", ""),
            # 知识管理
            "is_personal":     payload.get("is_personal", False),
            "trust_score":     payload.get("trust_score", 3),
            "knowledge_type":  payload.get("knowledge_type", ""),
            "tags":            payload.get("tags", []),
            "is_canonical":    payload.get("is_canonical", True),
            "relations":       payload.get("relations", []),
            "keywords":        payload.get("keywords", []),
            "auto_summary":    payload.get("auto_summary", ""),
            # 分组字段
            "timeline":        payload.get("timeline", {}),
            "origin":          payload.get("origin", {}),
            "stats":           payload.get("stats", {}),
            # 内容创作
            "target_platform": payload.get("target_platform", "none"),
            "related_product": payload.get("related_product", ""),
            "version":         payload.get("version", ""),
            # 系统字段
            "language":        payload.get("language", "zh"),
            "access_level":    payload.get("access_level", "private"),
            "batch_id":        payload.get("batch_id", ""),
            "is_archived":     payload.get("is_archived", False),
        })

    return {
        "ok": True,
        "query": query,
        "total": len(chunks),
        "chunks": chunks
    }


# ═══════════════════════════════════════════
# 报告输出（AI 综合回答 + 原始素材 → HTML → PDF）
# ═══════════════════════════════════════════

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "reports")

# ── LLM API 配置（OpenAI 兼容接口）──
LLM_BASE_URL = os.environ.get("KB_LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY  = os.environ.get("KB_LLM_API_KEY", "")
LLM_MODEL    = os.environ.get("KB_LLM_MODEL", "deepseek-chat")


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _call_llm_api(messages: list, base_url: str = None, api_key: str = None, model: str = None) -> str:
    """调用 OpenAI 兼容 Chat API，返回模型回复文本。"""
    base_url = (base_url or LLM_BASE_URL).rstrip("/")
    resp = requests.post(
        f"{base_url}/chat/completions",
        json={
            "model": model or LLM_MODEL,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 2048
        },
        headers={"Authorization": f"Bearer {api_key or LLM_API_KEY}"},
        timeout=120
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json_block(text: str) -> dict:
    """
    从 LLM 返回文本中提取并解析 JSON 对象（支持嵌套）。
    
    策略：
      1. 先尝试直接 json.loads()（LLM 可能返回纯净 JSON）
      2. 失败则找第一个 '{'，然后匹配花括号（计数深度），提取最外层 JSON
      3. 对提取的块尝试 json.loads()
    
    返回:
        dict — 解析成功
        None — 无法提取/解析
    """
    text = text.strip()
    
    # 策略1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 策略2：提取 JSON 块（匹配花括号）
    start = text.find("{")
    if start == -1:
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    json_end = -1
    
    for i in range(start, len(text)):
        ch = text[i]
        
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if in_string:
            if ch == '"':
                in_string = False
            continue
        
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break
    
    if json_end == -1:
        return None
    
    json_str = text[start:json_end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试修复常见错误：去掉尾部逗号
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*\]", "]", json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


# ═══════════════════════════════════════════
# 阶段二：标签形成引擎 — 三层管道
# Layer 1: 📎文件元数据 + 📐规则引擎 并行推断
# Layer 2: 合并仲裁 (file > rule > LLM > default) + LLM 兜底缺口
# Layer 3: 程序计算置信度 (非 LLM 自报)
# ═══════════════════════════════════════════

# ── T1: 核心数据结构常量 ──

# 来源置信度：每个来源固有的可信度
SOURCE_CONFIDENCE = {
    "file":    1.0,   # 文件自带元数据，最可信
    "rule":    0.85,  # 规则引擎命中，确定性高
    "llm":     0.60,  # LLM 推断 (temp=0 确定性，但语义有不确定性)
    "user":    1.0,   # 用户手动确认
    "default": 0.0,   # 智能默认值，未经验证
}

# 分面字段权重：用于计算整体置信度
FIELD_WEIGHTS = {
    "content_type":     0.25,
    "domain":           0.25,
    "temporal_nature":  0.20,
    "epistemic_status": 0.20,
    "keywords":         0.10,
}

# 必填分面字段列表
REQUIRED_FACET_FIELDS = ["content_type", "domain", "temporal_nature", "epistemic_status"]

# 智能默认值
SMART_DEFAULTS = {
    "content_type":     "knowledge",
    "domain":           [],
    "temporal_nature":  "timeboxed",
    "epistemic_status": "unverified",
    "lifecycle":        "published",
    "trust_score":      3,
    "keywords":         [],
    "title":            "",
    "author":           "",
    "auto_summary":     "",
    "is_personal":      False,
    "knowledge_type":   "",
    "udc_code":         "",
}


def _make_field(value, source: str, conf: float = None) -> dict:
    """创建一个带来源和置信度的字段。"""
    return {
        "value": value,
        "source": source,
        "confidence": conf if conf is not None else SOURCE_CONFIDENCE.get(source, 0.0),
    }


# ── T2: 规则引擎 ──

def match_rules(text: str, field_name: str) -> tuple:
    """
    对指定分面字段做规则匹配。
    
    返回:
        (value, source) — 命中时 value=规则值, source="rule"
        (None, None)    — 未命中
    
    注意: domain 是多选字段，返回的是 list（所有命中值的去重列表）。
    """
    rules = CLASSIFY_RULES.get(field_name, [])
    text_lower = text.lower()
    
    # domain 是多选 — 收集所有命中值
    if field_name == "domain":
        matched = []
        for rule in rules:
            hit = False
            for kw in rule["keywords"]:
                if kw.lower() in text_lower:
                    hit = True
                    break
            if not hit:
                for pattern in rule.get("patterns", []):
                    if re.search(pattern, text, re.IGNORECASE):
                        hit = True
                        break
            if hit and rule["value"] not in matched:
                matched.append(rule["value"])
        if matched:
            return matched, "rule"
        return None, None
    
    # 其他字段单选 — 返回第一个命中
    for rule in rules:
        for kw in rule["keywords"]:
            if kw.lower() in text_lower:
                return rule["value"], "rule"
        for pattern in rule.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                return rule["value"], "rule"
    return None, None


def match_all_rules(text: str) -> dict:
    """
    对全部 4 个分面字段做规则匹配，返回带来源标记的字段字典。
    
    返回:
        {
            "content_type":     AnnotatedField | None,
            "domain":           AnnotatedField | None,
            "temporal_nature":  AnnotatedField | None,
            "epistemic_status": AnnotatedField | None,
        }
        未命中的字段值为 None。
    """
    result = {}
    for field in REQUIRED_FACET_FIELDS:
        value, source = match_rules(text, field)
        if value is not None:
            result[field] = _make_field(value, source)
        else:
            result[field] = None
    return result


def extract_file_fields(file_metadata: dict) -> dict:
    """
    从文件元数据中提取可用字段（📎 file 来源）。
    
    文件元数据可能包含: title, author, content_type, keywords, source 等。
    只提取确实有值的字段。
    """
    if not file_metadata:
        return {}
    
    result = {}
    # title, author — 文件自带的标题和作者
    if file_metadata.get("title"):
        result["title"] = _make_field(file_metadata["title"], "file")
    if file_metadata.get("author"):
        result["author"] = _make_field(file_metadata["author"], "file")
    
    # content_type — 文件元数据可能指定类型
    if file_metadata.get("content_type"):
        result["content_type"] = _make_field(file_metadata["content_type"], "file")
    
    # keywords — 文件元数据可能包含关键词
    if file_metadata.get("keywords"):
        kws = file_metadata["keywords"]
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",") if k.strip()]
        result["keywords"] = _make_field(kws, "file")
    
    return result


# ── T3: LLM 兜底 — 仅对缺口字段调用 LLM ──

def call_llm_for_missing(text: str, missing_fields: list) -> dict:
    """
    调用 LLM 推断指定缺口字段（temperature=0，确定性输出）。
    LLM 只生成 missing_fields 中列出的字段，不生成 confidence。
    
    返回:
        dict — {"field_name": value, ...} 扁平值字典（不含来源标记）
        失败返回空 dict
    """
    if not missing_fields:
        return {}
    
    api_key = os.environ.get("KB_LLM_API_KEY") or LLM_API_KEY
    if not api_key:
        return {}
    
    sample = text[:5000].strip()
    if not sample:
        return {}
    
    from config.classifications import (
        CONTENT_TYPES, DOMAINS, TEMPORAL_NATURE, EPISTEMIC_STATUS,
        KNOWLEDGE_TYPES, TRUST_SCORE_LABELS,
    )
    
    # 动态构建 prompt — 只要求 missing_fields 中的字段
    field_descriptions = []
    if "content_type" in missing_fields:
        ct_list = "\n".join(f"  - {k}: {v}" for k, v in CONTENT_TYPES.items())
        field_descriptions.append(f'### content_type — 单选：\n{ct_list}')
    if "domain" in missing_fields:
        domain_list = "\n".join(f"  - {k}: {v}" for k, v in DOMAINS.items())
        field_descriptions.append(f'### domain — 可多选 0-3 个，不相关就空数组 []：\n{domain_list}')
    if "temporal_nature" in missing_fields:
        temporal_list = "\n".join(f"  - {k}: {v}" for k, v in TEMPORAL_NATURE.items())
        field_descriptions.append(f'### temporal_nature — 单选：\n{temporal_list}')
    if "epistemic_status" in missing_fields:
        epistemic_list = "\n".join(f"  - {k}: {v}" for k, v in EPISTEMIC_STATUS.items())
        field_descriptions.append(f'### epistemic_status — 单选：\n{epistemic_list}')
    if "keywords" in missing_fields:
        field_descriptions.append('### keywords — 3-8 个技术术语或关键概念')
    if "title" in missing_fields:
        field_descriptions.append('### title — 简要标题，不超过 50 字')
    if "author" in missing_fields:
        field_descriptions.append('### author — 作者/出处，没有则留空 ""')
    if "auto_summary" in missing_fields:
        field_descriptions.append('### auto_summary — 一句话摘要，不超过 100 字')
    if "trust_score" in missing_fields:
        trust_labels = "\n".join(f"  {k}: {v}" for k, v in TRUST_SCORE_LABELS.items())
        field_descriptions.append(f'### trust_score — 0-5 整数：\n{trust_labels}')
    if "knowledge_type" in missing_fields:
        ktype_list = "\n".join(f"  - {k}: {v}" for k, v in KNOWLEDGE_TYPES.items())
        field_descriptions.append(f'### knowledge_type — 单选：\n{ktype_list}')
    if "udc_code" in missing_fields:
        field_descriptions.append('### udc_code — UDC 细分码，如 "621"，不确定留空 ""')
    if "is_personal" in missing_fields:
        field_descriptions.append('### is_personal — true=个人经验/笔记，false=客观内容')
    if "lifecycle" in missing_fields:
        field_descriptions.append('### lifecycle — published/draft/review 等')
    
    # 构建示例 JSON — 只包含 missing_fields
    example_fields = {}
    for f in missing_fields:
        if f == "domain":
            example_fields[f] = ["0"]
        elif f == "keywords":
            example_fields[f] = ["关键词1", "关键词2"]
        elif f == "trust_score":
            example_fields[f] = 3
        elif f == "is_personal":
            example_fields[f] = False
        else:
            example_fields[f] = "value"
    example_json = json.dumps(example_fields, ensure_ascii=False)
    
    prompt = f"""你是一个知识分类专家。请分析以下文本，只填写以下字段：{", ".join(missing_fields)}

## 文本内容
{sample}

## 需要填写的字段
{chr(10).join(field_descriptions)}

## 输出格式
严格输出以下 JSON，不要包含任何额外文字、不要用 ```json 包裹：
{example_json}"""
    
    try:
        raw = _call_llm_api(
            [{"role": "user", "content": prompt}],
            base_url=os.environ.get("KB_LLM_BASE_URL") or LLM_BASE_URL,
            api_key=api_key,
            model=os.environ.get("KB_LLM_MODEL") or LLM_MODEL,
        )
    except Exception as e:
        logger.warning(f"call_llm_for_missing failed: {e}")
        return {}
    
    result = _extract_json_block(raw)
    if result is None:
        return {}
    
    # 只取 missing_fields 中的字段
    return {k: v for k, v in result.items() if k in missing_fields}


# ── T4: 合并仲裁 ──

def merge_parallel(file_fields: dict, rule_fields: dict) -> dict:
    """
    合并文件源和规则源的结果（并行产出，file 优先）。
    
    对每个字段：
        - 两源都有值 → file 优先 (file > rule)
        - 只有一源有值 → 用该源
        - 两源都没值 → 该字段为 None（等 LLM 兜底或 default）
    
    返回带来源标记的字段字典，未覆盖的字段值为 None。
    """
    all_keys = set(REQUIRED_FACET_FIELDS) | set(file_fields.keys()) | set(rule_fields.keys())
    merged = {}
    for key in all_keys:
        file_val = file_fields.get(key)
        rule_val = rule_fields.get(key)
        if file_val is not None:
            merged[key] = file_val
        elif rule_val is not None:
            merged[key] = rule_val
        else:
            merged[key] = None
    return merged


def fill_defaults(annotated: dict) -> dict:
    """
    对仍为 None 的字段填入智能默认值 (⚙️ default)。
    """
    for key, default_val in SMART_DEFAULTS.items():
        if annotated.get(key) is None or (isinstance(annotated.get(key), dict) and annotated[key].get("value") is None):
            annotated[key] = _make_field(default_val, "default")
    return annotated


# ── T5: 置信度计算 ──

def calculate_confidence(annotated: dict) -> float:
    """
    程序计算整体置信度：Σ(字段权重 × 字段来源置信度)。
    
    非分面字段（title/author/auto_summary 等）不参与计算，
    但影响是否调用 LLM（有值就不调用）。
    """
    total = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        field_data = annotated.get(field)
        if field_data and isinstance(field_data, dict):
            total += weight * field_data.get("confidence", 0.0)
    return round(total, 2)


# ── T6: classify_document() 主函数 ──

def classify_document(text: str, file_metadata: dict = None, project_source: str = "通用") -> dict:
    """
    阶段二标签形成主函数 — 三层管道。
    
    Layer 1: 📎文件元数据 + 📐规则引擎 并行推断（互不依赖）
    Layer 2: 合并仲裁 (file > rule) → 识别缺口 → 🤖LLM 兜底 (temp=0, 仅缺口) → ⚙️default 填剩余
    Layer 3: 程序计算置信度
    
    返回:
        {
            "ok": true/false,
            "classification": {  # 扁平值字典（兼容旧接口）
                "content_type", "domain", "temporal_nature", "epistemic_status",
                "keywords", "title", "author", "auto_summary", "trust_score",
                "knowledge_type", "udc_code", "is_personal", "lifecycle",
                "confidence": {"overall": float},
            },
            "annotated": {  # 带来源标记的完整结构（新接口）
                "content_type": AnnotatedField, ...
                "field_sources": {"content_type": "rule", ...},
                "overall_confidence": float,
            },
            "raw_response": "LLM原始输出(调试用, 可能为空)",
        }
    """
    # ── Layer 1: 两个源并行跑，互不依赖 ──
    file_fields = extract_file_fields(file_metadata)
    rule_fields = match_all_rules(text)
    
    # ── Layer 2: 合并 + 识别缺口 ──
    merged = merge_parallel(file_fields, rule_fields)
    
    # 识别仍为 None 或空值的分面字段 + 可选字段
    missing_facets = []
    for f in REQUIRED_FACET_FIELDS:
        field_data = merged.get(f)
        if field_data is None or (isinstance(field_data, dict) and not field_data.get("value")):
            missing_facets.append(f)
    
    # 可选字段也尝试让 LLM 补充
    optional_for_llm = ["keywords", "title", "author", "auto_summary", "trust_score",
                        "knowledge_type", "udc_code", "is_personal", "lifecycle"]
    missing_optional = [f for f in optional_for_llm if merged.get(f) is None]
    
    all_missing = missing_facets + missing_optional
    
    # LLM 只在有缺口时才调用，且只生成缺口字段
    raw_response = ""
    if all_missing:
        llm_result = call_llm_for_missing(text, all_missing)
        raw_response = str(llm_result) if llm_result else ""
        
        # 将 LLM 结果填入 merged（标记来源为 llm）
        for field, value in llm_result.items():
            if value is not None and value != "":
                merged[field] = _make_field(value, "llm")
    
    # 填充默认值
    fill_defaults(merged)
    
    # ── normalize 分面字段 ──
    # 提取扁平值做 normalize，再写回
    flat_for_normalize = {}
    for f in REQUIRED_FACET_FIELDS:
        fd = merged.get(f)
        if fd and isinstance(fd, dict):
            flat_for_normalize[f] = fd.get("value")
    normalize_facet_values(flat_for_normalize)
    # 写回
    for f in REQUIRED_FACET_FIELDS:
        if merged.get(f) and isinstance(merged[f], dict):
            merged[f]["value"] = flat_for_normalize.get(f, merged[f]["value"])
    
    # 校验 keywords 是 list
    kw_field = merged.get("keywords")
    if kw_field and isinstance(kw_field, dict):
        kw_val = kw_field.get("value", [])
        if not isinstance(kw_val, list):
            kw_val = [str(kw_val)] if kw_val else []
        kw_val = [str(k).strip()[:50] for k in kw_val if k]
        kw_field["value"] = kw_val
    
    # 校验 title/author/auto_summary 是 str
    for str_field in ["title", "author", "auto_summary"]:
        fd = merged.get(str_field)
        if fd and isinstance(fd, dict):
            fd["value"] = str(fd.get("value", "")).strip()[:200 if str_field == "auto_summary" else 100]
    
    # 校验 is_personal 是 bool
    ip_fd = merged.get("is_personal")
    if ip_fd and isinstance(ip_fd, dict):
        ip_val = ip_fd.get("value", False)
        if isinstance(ip_val, str):
            ip_fd["value"] = ip_val.strip().lower() in ("true", "yes", "1")
        else:
            ip_fd["value"] = bool(ip_val)
    
    # 校验 trust_score 是 0-5 int
    ts_fd = merged.get("trust_score")
    if ts_fd and isinstance(ts_fd, dict):
        try:
            ts_fd["value"] = max(0, min(5, int(ts_fd.get("value", 3))))
        except (ValueError, TypeError):
            ts_fd["value"] = 3
    
    # ── Layer 3: 程序计算置信度 ──
    overall_conf = calculate_confidence(merged)
    
    # 构建 field_sources 字典
    field_sources = {}
    for key, fd in merged.items():
        if fd and isinstance(fd, dict):
            field_sources[key] = fd.get("source", "default")
    
    # 构建扁平 classification（兼容旧接口）
    classification = {}
    for key in REQUIRED_FACET_FIELDS + ["keywords", "title", "author", "auto_summary",
                                         "trust_score", "knowledge_type", "udc_code",
                                         "is_personal", "lifecycle"]:
        fd = merged.get(key)
        if fd and isinstance(fd, dict):
            classification[key] = fd.get("value")
        else:
            classification[key] = SMART_DEFAULTS.get(key)
    
    classification["confidence"] = {"overall": overall_conf}

    # ── Layer 0: 系统自动填（language / project_source / source）──
    # 这些字段不参与 file > rule > llm 流程，由系统直接确定
    lang = detect_language(text)
    classification["language"] = lang

    classification["project_source"] = project_source

    if file_metadata and file_metadata.get("source"):
        src = file_metadata["source"]
    elif file_metadata:
        # 文件上传但没有显式 source — 用文件名或默认描述
        src_path = file_metadata.get("source_path", "")
        src = f"文件: {os.path.basename(src_path)}" if src_path else "文件上传"
    else:
        src = "手动输入"
    classification["source"] = src

    # 将 Layer 0 字段写入 merged（使 annoteted 也包含它们）
    merged["language"] = _make_field(lang, "system")
    merged["project_source"] = _make_field(project_source, "system")
    merged["source"] = _make_field(src, "system")

    return {
        "ok": True,
        "classification": classification,
        "annotated": {
            **merged,
            "field_sources": field_sources,
            "overall_confidence": overall_conf,
        },
        "raw_response": raw_response,
    }


def auto_classify(text: str, metadata: dict = None) -> dict:
    """
    兼容包装：调用 classify_document() 并返回与旧接口兼容的结构。
    
    阶段二已将标签形成逻辑重构为 classify_document() 三层管道。
    此函数保留以兼容现有调用方（main.py 等），内部转发到新实现。
    """
    result = classify_document(text, file_metadata=metadata)
    # 旧接口不返回 "annotated" 键，只返回 classification + raw_response
    return {
        "ok": result.get("ok", False),
        "classification": result.get("classification", {}),
        "annotated": result.get("annotated", {}),
        "raw_response": result.get("raw_response", ""),
    }


def _renumber_citations(synthesis: str, citation_keys: list) -> tuple[str, list[int]]:
    """
    正则提取回答中实际使用的引用编号，重编号为连续 1~N。
    返回 (重编号后文本, 实际使用的原始引用索引列表(1-based))。
    """

    # 兼容多种格式：[引用5] [引用 5] 引用5 引用 5
    used_raw = re.findall(r'\[?引用\s*(\d+)\]?', synthesis)
    if not used_raw:
        return synthesis, []

    # 去重保持首次出现顺序
    seen = set()
    used = []
    for x in used_raw:
        nx = int(x)
        if nx not in seen:
            seen.add(nx)
            used.append(nx)

    # 建立映射：原编号 → 新编号（按出现顺序从1开始）
    mapping = {old: new for new, old in enumerate(used, 1)}

    # 替换全文（兼容 [引用5] 和 引用5 两种格式）
    def _replace(match):
        old_num = int(match.group(1))
        new_num = mapping.get(old_num)
        if new_num is None:
            return match.group(0)
        orig = match.group(0)
        if orig.startswith('['):
            return f"[引用{new_num}]"
        else:
            return f"引用{new_num}"

    new_text = re.sub(r'\[?引用\s*(\d+)\]?', _replace, synthesis)
    return new_text, used


def _chunk_has_table(text: str) -> bool:
    """检测文本是否包含有效的 Markdown 管道表格。"""
    pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
    return len(pipe_lines) >= 3 and "---" in pipe_lines[1]


def _chunk_is_garbled(text: str) -> bool:
    """检测文本是否为 OCR 碎片（单字行、大量乱码）。"""
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return True
    # 过半行是单字或短碎片（≤3 字符且无 ASCII）→ 乱码
    short_count = sum(1 for l in lines if len(l.strip()) <= 3 and not any(c.isascii() and c.isprintable() and c not in "（）" for c in l))
    return short_count > len(lines) * 0.4


def _dedup_chunks(raw_chunks: list) -> list:
    """
    去重 + 质量过滤：
    - 同一 source 下，只要有管道表格版本，就丢弃同源的非表格版（OCR 降级碎片）
    - 同源同质量级别下，去重完全相同的文本
    - 保留原始得分排序
    """
    # 按 source 分组
    groups: dict[str, list] = {}
    for c in raw_chunks:
        src = c.get("source", "未知") or "未知"
        groups.setdefault(src, []).append(c)

    result = []
    for src, items in groups.items():
        tables = [c for c in items if _chunk_has_table(c["text"])]
        if tables:
            # 该 source 有管道表格 → 只保留表格版，丢弃非表格碎片
            candidates = tables
        else:
            # 纯文本 source → 丢弃乱码
            candidates = [c for c in items if not _chunk_is_garbled(c["text"])]

        if not candidates:
            continue

        # 去重完全相同的文本
        seen_text = set()
        for c in sorted(candidates, key=lambda c: c.get("score", 0), reverse=True):
            key = c["text"].strip()
            if key not in seen_text:
                seen_text.add(key)
                result.append(c)

    # 按原始分数降序
    result.sort(key=lambda c: c.get("score", 0), reverse=True)
    return result


def _expand_chunks(chunks: list, threshold: int = None) -> list:
    """
    展开 chunks：表格行数 > threshold 时，按行拆分为虚拟 chunk。
    返回展开后的 chunks 列表（长度 >= len(chunks)）。
    """
    if threshold is None:
        threshold = TABLE_SPLIT_THRESHOLD

    expanded = []
    for c in chunks:
        text = c["text"]
        pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
        is_table = len(pipe_lines) >= 3 and "---" in pipe_lines[1]

        if is_table and len(pipe_lines) - 2 > threshold:
            # 拆分：为每一行创建虚拟 chunk（浅拷贝，仅替换 text）
            for dl in pipe_lines[2:]:
                vc = dict(c)  # 浅拷贝，保留 images/source 等
                vc["text"] = f"{pipe_lines[0]}\n{pipe_lines[1]}\n{dl}"
                expanded.append(vc)
        else:
            expanded.append(c)

    return expanded


def _build_synthesis_prompt(query: str, chunks: list, table_split_threshold: int = None) -> tuple[str, list[str]]:
    """
    根据搜索结果构建 LLM 合成提示词。
    输入 chunks 已去重。
    如果 table_split_threshold 非空且某个表格 chunk 的行数 > 阈值，
    则将该表格按行拆分为多个迷你表引用（每行一个 [引用N]）。

    返回 (prompt_text, citation_keys)。
    """

    if table_split_threshold is None:
        table_split_threshold = TABLE_SPLIT_THRESHOLD

    # ── 展开 chunks（表格按行拆分） ──
    expanded = []  # list of (ref_id, src, text)

    for c in chunks:
        text = c["text"]
        src = c.get("source", "未知") or "未知"

        # 检测是否为管道表格
        pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
        is_table = len(pipe_lines) >= 3 and "---" in pipe_lines[1]

        if is_table and len(pipe_lines) - 2 > table_split_threshold:
            # 拆分：每行生成一个迷你表引用
            header_line = pipe_lines[0]
            sep_line = pipe_lines[1]
            data_lines = pipe_lines[2:]

            for dl in data_lines:
                mini = f"{header_line}\n{sep_line}\n{dl}"
                expanded.append((None, src, mini))  # ref_id 稍后统一编号
        else:
            # 不拆分，整块作为一条引用
            if len(text) > 1500:
                text = text[:1500] + "…(省略)"
            expanded.append((None, src, text))

    # 统一编号
    materials = []
    citation_keys = []
    for i, (_, src, text) in enumerate(expanded):
        ref_id = f"[引用{i+1}]"
        citation_keys.append(ref_id)
        materials.append(f"{ref_id} 来源:{src}\n{text}")

    materials_text = "\n\n---\n\n".join(materials)

    prompt = f"""你是知识库助手。请根据下面的参考资料，用中文直接回答用户的问题。

要求：
1. 从参考资料中提取相关信息，用自己的语言组织答案
2. 必须使用所有提供的参考资料（共{len(materials)}条），每个论断后面标注引用编号
3. 引用编号必须使用提供的 [引用1] [引用2] 等格式，不要自行编造编号
4. 如果某部分内容不是来自参考资料，而是你自己的推理或补充知识，请在句末标注 [补充]
5. 禁止编造参考资料中不存在的公式、数据、结论。[补充] 内容除外
6. 公式用 LaTeX 语法（行内 $...$，独行 $$...$$）
7. 如果参考资料不足以回答问题，请诚实说明
8. 回答字数控制在 300-800 字

用户问题：{query}

参考资料：
{materials_text}"""

    return prompt, citation_keys


def _img_to_b64(img_path: str, max_w: int = 800) -> str:
    """
    将图片文件转为 base64 data URI，嵌入 HTML 使用。
    自动缩小到 max_w 像素以内（避免 HTML 文件过大）。
    失败返回空字符串。
    
    D5 修复：支持相对路径（相对于 PROJECT_DIR）
    """
    # D5 修复：如果路径是相对的，转换为绝对路径
    if not os.path.isabs(img_path):
        img_path = os.path.join(PROJECT_DIR, img_path)
    
    if HAS_PIL:
        try:
            with PILImage.open(img_path) as im:
                w, h = im.size
                if w > max_w:
                    ratio = max_w / w
                    im = im.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format=im.format or "PNG")
                data = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            try:
                with open(img_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
            except Exception:
                return ""
    else:
        try:
            with open(img_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
        except Exception:
            return ""
    ext = os.path.splitext(img_path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(ext, "image/png")
    return f"data:{mime};base64,{data}"


# ── KaTeX 服务端渲染 ──
_KATEX_CSS = None
_NODE_BIN = os.environ.get("KB_NODE_BIN") or "node"
_NPM_ROOT = os.environ.get("KB_NPM_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_modules")
_KATEX_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_math.js")

def _katex_css() -> str:
    """返回 KaTeX CSS（惰性加载，只读一次）。"""
    global _KATEX_CSS
    if _KATEX_CSS is None:
        css_path = os.path.join(_NPM_ROOT, "katex", "dist", "katex.min.css")
        try:
            with open(css_path, "r", encoding="utf-8") as f:
                _KATEX_CSS = f.read()
        except FileNotFoundError:
            _KATEX_CSS = ""
    return _KATEX_CSS


def _katex_post_process(html: str) -> str:
    """将 HTML 中的 <span class="formula-block">... 和 <span class="formula-inline">...
    批量渲染为 KaTeX HTML。失败时保留原始 span作为兜底。"""
    # 收集所有公式
    formulas = []
    pattern = re.compile(
        r'<span class="formula-(block|inline)">(.*?)</span>',
        re.DOTALL
    )

    for m in pattern.finditer(html):
        display = (m.group(1) == "block")
        text = m.group(2).strip()
        if text:
            formulas.append({
                "text": text,
                "display": display,
                "start": m.start(),
                "end": m.end(),
                "original": m.group(0)
            })

    if not formulas:
        return html

    # 写入临时 JSON
    fd, tmp_in = tempfile.mkstemp(suffix=".json", prefix="katex_in_")
    os.close(fd)
    fd, tmp_out = tempfile.mkstemp(suffix=".json", prefix="katex_out_")
    os.close(fd)
    try:
        batch = [{"text": f["text"], "display": f["display"]} for f in formulas]
        with open(tmp_in, "w", encoding="utf-8") as f:
            json.dump({"formulas": batch}, f, ensure_ascii=False)

        env = os.environ.copy()
        env["NODE_PATH"] = _NPM_ROOT
        result = subprocess.run(
            [_NODE_BIN, _KATEX_SCRIPT, tmp_in, tmp_out],
            capture_output=True, text=True, timeout=30, env=env
        )
        if result.returncode != 0:
            return html  # Node.js 失败，保留原始 span

        with open(tmp_out, "r", encoding="utf-8") as f:
            output = json.load(f)

        # 替换：从后往前替换以保持位置正确
        results = output.get("results", [])
        if len(results) != len(formulas):
            return html  # 数量不匹配

        parts = []
        last_end = 0
        for i, fm in enumerate(formulas):
            r = results[i]
            parts.append(html[last_end:fm["start"]])
            if r.get("ok"):
                parts.append(r["html"])
            else:
                parts.append(fm["original"])  # 回退到原始 span
            last_end = fm["end"]
        parts.append(html[last_end:])
        return "".join(parts)

    finally:
        for p in (tmp_in, tmp_out):
            try:
                os.unlink(p)
            except OSError:
                pass


# ── 公式文本 → HTML span 工具函数 ──
FORMULA_BLOCK_RE = re.compile(r'\$\$([\s\S]+?)\$\$')
FORMULA_INLINE_RE = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')


def _formula_to_html_spans(text: str) -> str:
    """将 LaTeX 公式转为 <span class="formula-block/inline"> 标记，供 KaTeX 后处理。"""
    text = FORMULA_BLOCK_RE.sub(r'<span class="formula-block">\1</span>', text)
    text = FORMULA_INLINE_RE.sub(r'<span class="formula-inline">\1</span>', text)
    return text


def _render_report_html(query: str, synthesis: str, chunks: list, output_dir: str, used: list = None, citation_keys: list = None) -> str:
    """
    渲染两层报告 HTML：上层 AI 回答 + 下层原始素材。
    返回 HTML 文件路径。
    """
    import html as _html

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_query = re.sub(r'[\\/*?:"<>|]', '_', query)[:40]

    # ── 上层：AI 回答（引用编号高亮） ──
    # 注意：不对 synthesis 做 HTML 转义，保留 $...$ 供 MathJax 渲染
    # LLM 输出是可信的；若含 < > 等字符会被 MathJax/浏览器安全处理
    synthesis_html = synthesis
    # 双换行为段落
    synthesis_html = re.sub(r'\n\n+', '</p><p>', synthesis_html)
    synthesis_html = synthesis_html.replace('\n', '<br>')
    if not synthesis_html.startswith('<p>'):
        synthesis_html = '<p>' + synthesis_html
    if not synthesis_html.endswith('</p>'):
        synthesis_html = synthesis_html + '</p>'

    # 引用编号加样式→跳转锚点
    synthesis_html = re.sub(
        r'\[引用(\d+)\]',
        r'<a href="#ref\1" class="citation">[引用\1]</a>',
        synthesis_html
    )

    # 公式：先处理 $$..$$（多行），再处理 $..$（单行，排除 $$ 边界）
    synthesis_html = _formula_to_html_spans(synthesis_html)

    # ── 收集所有图片路径 ──
    all_images = []
    for c in chunks:
        for img in c.get("images", []):
            if img and os.path.isfile(img) and img not in all_images:
                all_images.append(img)

    # ── 下层：原始素材（每条 chunk 都展示，按 source+chunk_index 去重） ──

    def _img_tag(img_path: str, max_w: int = 700) -> str:
        """将图片路径转为 base64 <img> 标签，失败返回原路径 file:// 引用。"""
        b64 = _img_to_b64(img_path, max_w=max_w)
        if b64:
            return f'<br><img src="{b64}" class="evidence-img"><br>'
        # 降级：file:// 引用（桌面可能还能打开）
        return f'<br><img src="file://{_html.escape(img_path)}" class="evidence-img"><br>'


    def _format_evidence_text(text: str) -> str:
        """格式化原始素材文本为 HTML：表格自动转 <table>，公式/图片引用包裹。"""
        lines = text.split('\n')

        # —— 先尝试整个文本是否为管道表格（过滤所有以 | 开头的行） ——
        pipe_lines = [l for l in lines if l.strip().startswith('|')]
        if len(pipe_lines) >= 3 and '---' in pipe_lines[1]:
            # 有效表格：整个文本渲染为一张 HTML table
            return _pipe_table_to_html(pipe_lines)

        # 非表格文本：逐行处理
        result = []
        for line in lines:
            # 先转义 HTML（防 XSS），再还原公式和图片引用
            escaped = _html.escape(line)
            # 还原 [image: ...] → <img> 标签
            escaped = re.sub(
                r'\[image:\s*([^\]]+)\]',
                lambda m: _img_tag(m.group(1).strip()),
                escaped
            )
            # 还原 $...$ 和 $$...$$ → formula <span>
            escaped = _formula_to_html_spans(escaped)
            result.append(escaped)
        return '\n'.join(result)

    def _pipe_table_to_html(pipe_lines: list) -> str:
        """将 Markdown 管道表格行列表转为 HTML <table>。列宽由内容预计算。"""
        def _cell_html(raw: str) -> str:
            """处理 table cell: 先转义HTML防XSS，再还原公式和图片引用。"""
            s = _html.escape(raw)
            # 还原公式 $...$ 和 $$...$$
            s = _formula_to_html_spans(s)
            # 还原图片引用 [image: ...] → <img>
            s = re.sub(r'\[image:\s*(.+?)\]', lambda m: _img_tag(m.group(1).strip()), s)
            return s

        rows = []
        for pl in pipe_lines:
            cells = pl.strip().strip('|').split('|')
            rows.append([c.strip() for c in cells])
        data_rows = [rows[0]] + rows[2:]  # skip separator row

        # ── 预计算列宽百分比 ──
        ncols = max(len(r) for r in data_rows) if data_rows else 0
        if ncols > 0:
            col_widths_ch = [0.0] * ncols
            for row in data_rows:
                for i, cell in enumerate(row):
                    if i >= ncols:
                        break
                    w = sum(2.0 if ord(c) > 127 else 1.0 for c in cell)
                    if w > col_widths_ch[i]:
                        col_widths_ch[i] = w
            total_ch = sum(col_widths_ch)
            if total_ch > 0:
                col_pcts = [max(5.0, w / total_ch * 100.0) for w in col_widths_ch]
                pct_sum = sum(col_pcts)
                col_pcts = [p / pct_sum * 100.0 for p in col_pcts]
            else:
                col_pcts = [100.0 / ncols] * ncols
            colgroup = '<colgroup>' + ''.join(f'<col style="width:{p:.1f}%">' for p in col_pcts) + '</colgroup>'
        else:
            colgroup = ''

        html_parts = ['<div class="md-table-wrap"><table class="md-table">', colgroup]
        for ri, row in enumerate(data_rows):
            tag = 'th' if ri == 0 else 'td'
            html_parts.append('<tr>')
            for cell in row:
                html_parts.append(f'<{tag}>{_cell_html(cell)}</{tag}>')
            html_parts.append('</tr>')
        html_parts.append('</table></div>')
        return ''.join(html_parts)

    raw_sections = []
    for i, c in enumerate(chunks):
        # 计算 ref_id（锚点 ID）和 ref_tag（引用标签）
        orig_num = i + 1
        ref_id = f"ref{orig_num}"
        ref_tag = ""
        if used is not None:
            if orig_num in used:
                new_num = used.index(orig_num) + 1
                ref_id = f"ref{new_num}"
                ref_tag = f'<span class="ref-tag">[引用{new_num}]</span>'
            else:
                ref_id = f"ref{orig_num}-unused"
        else:
            ref_tag = f'<span class="ref-tag">[引用{orig_num}]</span>'

        src = c.get("source", "未知") or "未知"

        text_html = _format_evidence_text(c["text"])
        score = c.get("score", 0)
        images_list = c.get("images", [])

        images_html = ""
        if images_list:
            imgs_parts = []
            for img in images_list:
                if not (img and os.path.isfile(img)):
                    continue
                b64 = _img_to_b64(img, max_w=700)
                if b64:
                    imgs_parts.append(f'<div class="ev-img-wrap"><img src="{b64}" class="evidence-img"></div>')
            if imgs_parts:
                images_html = f'<div class="evidence-images">{"".join(imgs_parts)}</div>'

        raw_sections.append(f"""
        <div class="evidence-item" id="{ref_id}">
            <div class="evidence-header">
                {ref_tag}
                <span class="evidence-source">{_html.escape(src)}</span>
                <span class="evidence-score">相关度: {score:.0%}</span>
            </div>
            <div class="evidence-text">{text_html}</div>
            {images_html}
        </div>""")

    # ── 完整 HTML ──
    all_images_html = ""
    katex_css = _katex_css()
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
<title>知识库报告：{_html.escape(query[:60])}</title>
<style>
  :root {{ --bg: #f8f9fa; --card: #fff; --text: #222; --muted: #666; --accent: #1a6fb5; --border: #e0e0e0; --formula-bg: #f0f4f8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1a1a2e; --card: #16213e; --text: #e0e0e0; --muted: #999; --accent: #7ec8e3; --border: #333; --formula-bg: #0f1928; }} }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; font-size: 15px; -webkit-text-size-adjust: 100%; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 32px 20px 80px; }}

  .toolbar {{ position: sticky; top: 0; z-index: 100; background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }}
  .toolbar span {{ color: var(--muted); font-size: 13px; }}
  .btn-download {{ background: var(--accent); color: #fff; border: none; padding: 8px 20px; border-radius: 6px; font-size: 14px; cursor: pointer; }}
  .btn-download:hover {{ opacity: 0.85; }}

  .query-title {{ font-size: 22px; font-weight: 700; margin: 24px 0 8px; }}
  .query-meta {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}

  .section {{ margin: 32px 0; }}
  .section h2 {{ font-size: 18px; color: var(--accent); border-bottom: 2px solid var(--border); padding-bottom: 8px; margin-bottom: 16px; }}

  .synthesis {{ background: var(--card); border-radius: 8px; padding: 24px; border: 1px solid var(--border); }}
  .synthesis p {{ margin: 8px 0; }}
  .citation {{ color: var(--accent); text-decoration: none; font-weight: 600; font-size: 13px; vertical-align: super; }}
  .citation:hover {{ text-decoration: underline; }}
  .formula-block {{ display: block; background: var(--formula-bg); padding: 10px 16px; border-radius: 4px; margin: 8px 0; font-family: "Times New Roman", serif; font-size: 16px; overflow-x: auto; }}
  .formula-inline {{ font-family: "Times New Roman", "Cambria Math", serif; font-style: italic; color: #1a5c8a; background: rgba(26,111,181,0.06); padding: 1px 4px; border-radius: 3px; word-break: keep-all; }}

  .evidence-item {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin: 16px 0; }}
  .evidence-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }}
  .ref-tag {{ background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; flex-shrink: 0; }}
  .evidence-source {{ color: var(--muted); font-size: 13px; }}
  .evidence-score {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .evidence-text {{ font-size: 14px; line-height: 1.8; word-break: break-word; }}
  .evidence-images {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
  .evidence-images img, .evidence-img {{ max-width: 100%; max-height: 400px; object-fit: contain; border: 1px solid var(--border); border-radius: 4px; margin: 6px 0; display: block; }}

  .md-table-wrap {{ max-width: 100%; overflow-x: auto; margin: 10px 0; -webkit-overflow-scrolling: touch; }}
  .md-table {{ border-collapse: collapse; font-size: 13px; table-layout: fixed; width: 100%; }}
  .md-table th {{ background: var(--formula-bg); color: var(--text); padding: 8px 10px; border: 1px solid var(--border); text-align: left; font-weight: 600; overflow-wrap: break-word; }}
  .md-table td {{ padding: 8px 10px; border: 1px solid var(--border); vertical-align: top; word-break: break-word; overflow-wrap: break-word; }}
  .md-table tr:nth-child(even) td {{ background: rgba(128,128,128,0.04); }}

  @media (max-width: 600px) {{
    .container {{ padding: 16px 12px 60px; }}
    .evidence-item {{ padding: 14px; }}
    .md-table {{ font-size: 12px; }}
    .md-table th, .md-table td {{ padding: 6px 8px; }}
    .formula-block {{ padding: 8px 10px; font-size: 14px; }}
    .evidence-images img, .evidence-img {{ max-height: 280px; }}
    .query-title {{ font-size: 18px; }}
    .toolbar {{ padding: 10px 16px; }}
  }}

  @media print {{
    .toolbar {{ display: none; }}
    body {{ background: #fff; color: #000; font-size: 12px; }}
    .container {{ max-width: 100%; padding: 0; }}
    .evidence-item, .synthesis {{ box-shadow: none; break-inside: avoid; }}
    .md-table-wrap {{ overflow-x: visible; }}
    .md-table {{ width: 100%; font-size: 11px; }}
  }}
{katex_css}
</style>
</head>
<body>
<div class="toolbar">
  <span>生成时间: {now_str}</span>
  <button class="btn-download" onclick="window.print()">📥 下载 PDF / 打印</button>
</div>
<div class="container">
  <h1 class="query-title">{_html.escape(query)}</h1>
  <p class="query-meta">知识库检索 · {len(chunks)} 条匹配 · {now_str}</p>
  <div class="section">
    <h2>📝 综合回答</h2>
    <div class="synthesis">{synthesis_html}</div>
  </div>
  <div class="section">
    <h2>📚 原始素材</h2>
    {"".join(raw_sections)}
  </div>
  {all_images_html}
</div>
</body>
</html>"""

    # KaTeX 服务端渲染：批量转换所有 $...$ 公式
    html = _katex_post_process(html)

    _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}.html"
    html_path = os.path.join(output_dir, filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path


def answer(
    query: str,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
    model: str = EMBED_MODEL,
    threshold: float = 0.3,
    llm_model: str = None,
    llm_base_url: str = None,
    llm_api_key: str = None,
    output_dir: str = None,
    table_split_threshold: int = None,
    facet_filter: dict = None,
) -> dict:
    """
    端到端知识库问答：搜索 → LLM API 合成 → HTML 报告（KaTeX 公式渲染）。

    参数:
        facet_filter: 分面过滤条件（见 search() 函数说明）
    """
    output_dir = output_dir or OUTPUT_DIR
    # 从 os.environ 实时读取（避免 .env 加载顺序导致的空值）
    llm_model = llm_model or os.environ.get("KB_LLM_MODEL") or LLM_MODEL
    llm_base_url = llm_base_url or os.environ.get("KB_LLM_BASE_URL") or LLM_BASE_URL
    llm_api_key = llm_api_key or os.environ.get("KB_LLM_API_KEY") or LLM_API_KEY

    if not llm_base_url or not llm_api_key:
        return {
            "ok": False,
            "error": "未配置 LLM API。请设置环境变量 KB_LLM_BASE_URL/KB_LLM_API_KEY 或传入 --llm-base-url/--llm-api-key。"
        }

    # 1. 搜索（单集合方案）
    sr = search(query, top_k=top_k, collection=collection,
                 score_threshold=threshold, model=model,
                 facet_filter=facet_filter)
    raw_chunks = sr.get("chunks", [])

    if not sr.get("ok"):
        return {"ok": False, "error": sr.get("error", "搜索失败")}

    if not raw_chunks:
        return {"ok": True, "query": query, "synthesis": "知识库中未找到相关内容。", "chunks": [], "html": None}

    # 1.5 去重
    chunks = _dedup_chunks(raw_chunks)

    # 2. LLM 合成
    prompt_text, citation_keys = _build_synthesis_prompt(query, chunks, table_split_threshold=table_split_threshold)
    # 展开 chunks（表格按行拆分后与 citation_keys 一一对应）
    expanded_chunks = _expand_chunks(chunks, table_split_threshold)
    try:
        synthesis = _call_llm_api(
            [{"role": "user", "content": prompt_text}],
            base_url=llm_base_url, api_key=llm_api_key, model=llm_model
        )
    except Exception as e:
        synthesis = f"（LLM 调用失败：{e}。以下为原始检索结果。）"

    # 2.5 引用重编号（使编号连续不跳跃）
    synthesis, used = _renumber_citations(synthesis, citation_keys)

    # 3. 生成 HTML 报告
    try:
        html_path = _render_report_html(query, synthesis, expanded_chunks, output_dir, used=used, citation_keys=citation_keys)
    except Exception as e:
        return {"ok": False, "error": f"HTML 报告生成失败: {e}", "synthesis": synthesis, "chunks": chunks}

    return {"ok": True, "query": query, "synthesis": synthesis, "html": html_path, "chunks": expanded_chunks}


# ═══════════════════════════════════════════
# 知识管理函数 (v4.0)
# ═══════════════════════════════════════════

def get_facet_stats(collection: str = DEFAULT_COLLECTION) -> dict:
    """
    获取知识库的分面维度统计。

    返回:
        {
            "ok": true,
            "total_points": N,
            "facets": {
                "content_type": {"knowledge": 120, "standard": 15, ...},
                "domain":        {"0": 45, "6": 30, ...},
                "temporal_nature": {"evergreen": 80, "timeboxed": 12, ...},
                "epistemic_status":{"corroborated": 50, "unverified": 30, ...},
            },
            "meta": {
                "avg_trust": 3.2,
                "personal_count": 5,
                "archived_count": 0,
            }
        }
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 获取 points_count
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        if info.status_code != 200:
            return {"ok": False, "error": f"集合 {collection} 不存在"}

        total_pts = info.json()["result"]["points_count"]
        if total_pts == 0:
            return {"ok": True, "total_points": 0, "facets": {}, "meta": {}}

        facets = {}
        meta_stats = {}

        # ── 分面分布统计 ──
        # S5 fix: 边 scroll 边聚合，不积累全量 points 到内存
        scroll_limit = 1000
        offset = 0
        ct_count = defaultdict(int)
        domain_count = defaultdict(int)
        tn_count = defaultdict(int)
        ep_count = defaultdict(int)
        trust_sum = 0
        trust_n = 0
        personal_n = 0
        archived_n = 0

        while offset < total_pts:
            try:
                resp = requests.post(
                    f"{QDRANT_URL}/collections/{collection}/points/scroll",
                    json={"limit": scroll_limit, "offset": offset,
                          "with_payload": True, "with_vector": False},
                    timeout=30
                )
                batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
                if not batch:
                    break
                # 逐批聚合，不保存到内存
                for p in batch:
                    pl = p.get("payload", {})
                    ct = pl.get("content_type", "unknown")
                    ct_count[ct] += 1

                    for d in pl.get("domain", []):
                        domain_count[d] += 1

                    tn = pl.get("temporal_nature", "")
                    if tn:
                        tn_count[tn] += 1

                    ep = pl.get("epistemic_status", "")
                    if ep:
                        ep_count[ep] += 1

                    ts = pl.get("trust_score")
                    if ts is not None:
                        trust_sum += ts
                        trust_n += 1

                    if pl.get("is_personal", False):
                        personal_n += 1

                    if pl.get("is_archived", False):
                        archived_n += 1

                offset += len(batch)
            except Exception:
                break

        facets["content_type"] = dict(ct_count)
        facets["domain"] = dict(domain_count)
        facets["temporal_nature"] = dict(tn_count)
        facets["epistemic_status"] = dict(ep_count)

        meta_stats["avg_trust"] = round(trust_sum / trust_n, 1) if trust_n > 0 else 0
        meta_stats["personal_count"] = personal_n
        meta_stats["archived_count"] = archived_n

        return {
            "ok": True,
            "total_points": total_pts,
            "facets": facets,
            "meta": meta_stats,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═════════════════════════════════════════
# CLI 入口
# ═════════════════════════════════════════

if __name__ == "__main__":
    # 修复 Windows GBK 环境下 print 非 ASCII 字符崩溃问题
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description="WorkBuddy 知识库引擎")
    parser.add_argument("query", nargs="*", help="搜索查询")
    parser.add_argument("--top", type=int, default=5, help="返回结果数")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="集合名称")
    parser.add_argument("--ingest", default=None, help="摄入文件路径")
    parser.add_argument("--text", default=None, help="直接摄入文本内容（与 --source 配合）")
    parser.add_argument("--ocr", default=None, help="OCR 图片路径")
    parser.add_argument("--engine", default="paddle", choices=["paddle", "tesseract", "structured"], help="OCR 引擎")
    parser.add_argument("--check-only", action="store_true", help="只 OCR 不入库")
    parser.add_argument("--llm-optimize", action="store_true", help="用LLM优化OCR结果（自动修复错别字）")
    parser.add_argument("--source", default=None, help="来源标识")
    parser.add_argument("--answer", action="store_true", help="端到端问答")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名")
    parser.add_argument("--llm-base-url", default=None, help="LLM API 地址")
    parser.add_argument("--llm-api-key", default=None, help="LLM API Key")
    parser.add_argument("--threshold", type=float, default=0.3, help="相关度阈值")
    parser.add_argument("--table-split-threshold", type=int, default=None, help="表格行拆分阈值（默认用 TABLE_SPLIT_THRESHOLD）")
    parser.add_argument("--model", default=EMBED_MODEL, help="嵌入模型")
    parser.add_argument("--output", default=None, help="输出目录")
    args = parser.parse_args()

    query_str = " ".join(args.query) if isinstance(args.query, list) else args.query

    if args.ocr:
        # 导入OCR工作流
        try:
            from ocr_workflow import do_ocr
            do_ocr(
                image_path=args.ocr,
                source=args.source or "",
                engine=args.engine,
                check_only=args.check_only,
                collection=args.collection,
                model=args.model,
                llm_optimize=args.llm_optimize,
                llm_api_key=args.llm_api_key or os.environ.get("KB_LLM_API_KEY", ""),
                llm_base_url=args.llm_base_url or os.environ.get("KB_LLM_BASE_URL", ""),
                llm_model=args.llm_model or os.environ.get("KB_LLM_MODEL", "deepseek-chat")
            )
        except ImportError:
            print("❌ 错误: ocr_workflow.py 未找到。请确保 ocr_workflow.py 在同一目录下。")
            sys.exit(1)
    elif args.ingest:
        result = ingest(file_path=args.ingest, metadata={"source": args.source or ""}, collection=args.collection, model=args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.text and args.source:
        result = ingest(text=args.text, metadata={"source": args.source}, collection=args.collection, model=args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif query_str and args.answer:
        result = answer(
            query_str,
            top_k=args.top,
            collection=args.collection,
            model=args.model,
            threshold=args.threshold,
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            llm_api_key=args.llm_api_key,
            output_dir=args.output,
            table_split_threshold=args.table_split_threshold
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif query_str:
        result = search(
            query_str,
            top_k=args.top,
            collection=args.collection,
            model=args.model,
            score_threshold=args.threshold
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()
