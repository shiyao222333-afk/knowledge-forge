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
from search_engine import (
    search, answer,
    _call_llm_api, _extract_json_block,
    _build_synthesis_prompt, _render_report_html,
    _renumber_citations, _dedup_chunks, _expand_chunks,
    _chunk_has_table, _chunk_is_garbled,
    _img_to_b64, _katex_css, _katex_post_process, _formula_to_html_spans,
    _ensure_output_dir,
    TABLE_SPLIT_THRESHOLD,
    OUTPUT_DIR, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
)

__version__ = "0.7.0-dev"



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
