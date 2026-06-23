"""
Ingest Pipeline — Qdrant payload builder.

Extracted from kb_query.py (v0.7.0 B1 refactor).

职责:
  build_payloads() — 将文本/块/向量/元数据组装为 Qdrant points 列表
  不负责: 文本提取、分块、嵌入计算、Qdrant 写入（由 kb_query.ingest() 协调）
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from qconst import PROJECT_DIR
from text_pipeline import _text_hash, _detect_language
from config.classifications import normalize_facet_values


def build_payloads(
    text: str,
    chunks: list,
    vectors: list,
    sparse_vectors: Optional[list] = None,
    base_meta: Optional[dict] = None,
    file_path: str = "",
    source: str = "unknown",
    model: str = "",
) -> dict:
    """
    构建 Qdrant points 列表（含完整 payload）。

    参数:
        text:       原始全文（用于 content_hash 和语言检测）
        chunks:     已切块的文本列表
        vectors:    嵌入向量列表（与 chunks 一一对应）
        base_meta:  用户提供的元数据字典
        file_path:  原始文件路径
        source:     来源标识
        model:      嵌入模型名

    返回:
        {"ok": True, "points": [...], "doc_id": "...",
         "content_hash": "...", "valid_images": [...], "ingested_at": "..."}
    """
    base_meta = base_meta or {}
    # doc_id: 文档级唯一标识（完整 UUID，非截短）
    doc_id = base_meta.get("doc_id") or str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc).isoformat()
    full_text_hash = _text_hash(text)

    # ── 分面字段（调用 normalize_facet_values 做枚举守卫）──
    facet_raw = {
        "content_type":     base_meta.get("content_type", "knowledge"),
        "domain":           base_meta.get("domain", []),
        "temporal_nature":  base_meta.get("temporal_nature", "timeboxed"),
        "epistemic_status": base_meta.get("epistemic_status", "unverified"),
    }
    facet_norm = normalize_facet_values(facet_raw)
    content_type     = facet_norm["content_type"]
    domain           = facet_norm["domain"] if isinstance(facet_norm["domain"], list) else [facet_norm["domain"]]
    temporal_nature  = facet_norm["temporal_nature"]
    epistemic_status = facet_norm["epistemic_status"]

    # ── 生命周期（普通字段）──
    lifecycle      = base_meta.get("lifecycle", "published")
    project_source = base_meta.get("project_source", "")

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
    needs_review = base_meta.get("needs_review", False)

    # ── 阶段二新增：字段来源 + 置信度 ──
    field_sources_payload = base_meta.get("field_sources", {})
    confidence_payload = base_meta.get("confidence_overall", None)

    # 有效图片引用（由调用方传入预计算的值）
    valid_images = base_meta.get("_valid_images", [])

    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        # 每个 chunk 用随机 64-bit ID（不依赖 Qdrant points_count，零并发冲突）
        point_id = uuid.uuid4().int >> 64
        point = {
            "id": point_id,
            "vector": vec,  # 稠密向量（plain array）
            "payload": {
                # ── 内容字段 ──
                "text": chunk,
                "title": title,
                "source": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "doc_id": doc_id,
                "doc_uid": doc_id,
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
                    "source_path": file_path or "",
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
        }
        # ── 稀疏向量（命名向量 "bm25"，独立于稠密向量）──
        if sparse_vectors and i < len(sparse_vectors):
            point["sparse_vectors"] = {
                "bm25": {
                    "indices": sparse_vectors[i][0],
                    "values": sparse_vectors[i][1]
                }
            }
        points.append(point)

    return {
        "ok": True,
        "points": points,
        "doc_id": doc_id,
        "content_hash": full_text_hash,
        "valid_images": valid_images,
        "ingested_at": ingested_at,
    }
