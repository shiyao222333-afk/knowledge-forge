"""
Citrinitas · 熔知 — 文档管理器

文档 CRUD + 摄入日志管理。
所有函数返回统一的 {"ok": bool, ...} 格式。
"""

import os
import json
import requests
import logging
from qconst import QDRANT_URL, DEFAULT_COLLECTION, INGEST_LOG_PATH, _check_qdrant

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 摄入日志
# ═══════════════════════════════════════════

def _log_ingest(entry: dict):
    """
    摄入成功后写一行日志到 ingest_log.jsonl。
    entry 格式:
    {
        "source_file": "D:/data/齿轮设计.txt",   # 原始文件路径（绝对路径）
        "source_text": null,                    # 手动输入时为文本内容（前 500 字）
        "collection": "TH",
        "doc_id": "a1b2c3d4",
        "content_hash": "f3e8a...",
        "embed_model": "qwen3-embedding:4b",
        "ingested_at": "2026-06-14T12:00:00Z"
    }
    """
    try:
        os.makedirs(os.path.dirname(INGEST_LOG_PATH), exist_ok=True)
        with open(INGEST_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[IngestLog] 日志写入失败（可忽略）: {e}")


def read_ingest_log() -> list[dict]:
    """
    读取摄入日志，返回所有记录列表。
    如果文件不存在或格式错误，返回空列表。
    """
    if not os.path.isfile(INGEST_LOG_PATH):
        return []
    entries = []
    try:
        with open(INGEST_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception as e:
                    logger.warning(f"[Scroll] 分页读取失败（跳过此页）: {e}")
                    continue
        return entries
    except Exception:
        return []


# ═══════════════════════════════════════════
# 文档 CRUD
# ═══════════════════════════════════════════

def update_metadata(
    doc_id: str,
    updates: dict,
    collection: str = DEFAULT_COLLECTION,
) -> dict:
    """
    更新指定文档所有 chunk 的 Payload 字段。

    参数:
        doc_id: 文档 ID
        updates: 要更新的字段 dict，如 {"trust_score": 5, "is_archived": true}
        collection: 集合名

    返回:
        {"ok": true, "updated": N, "doc_id": "..."}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 1. 找出该 doc_id 的所有 point
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"搜索失败: {resp.status_code}"}

        points = resp.json()["result"]["points"]
        if not points:
            return {"ok": False, "error": f"未找到 doc_id={doc_id} 的记录"}

        # 2. 用 set_payload API 批量更新（key-level merge，不会覆盖其他字段）
        all_point_ids = [p["id"] for p in points]

        put_resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/payload",
            json={"payload": updates, "points": all_point_ids},
            timeout=10
        )
        if put_resp.status_code != 200:
            return {"ok": False, "error": f"更新失败: {put_resp.status_code}"}

        return {"ok": True, "updated": len(points), "doc_id": doc_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def set_doc_relations(
    doc_id: str,
    add_relations: list = None,
    remove_relations: list = None,
    collection: str = DEFAULT_COLLECTION,
) -> dict:
    """
    管理文档的关系字段。

    参数:
        doc_id: 文档 ID
        add_relations: 要添加的关系列表 [{"type": "similar", "doc_id": "xxx"}, ...]
        remove_relations: 要移除的关系列表（按 {"type": "x", "doc_id": "y"} 匹配）
        collection: 集合名

    返回:
        {"ok": true, "updated": N, "doc_id": "..."}
    """
    add_relations = add_relations or []
    remove_relations = remove_relations or []

    if not add_relations and not remove_relations:
        return {"ok": False, "error": "请提供 add_relations 或 remove_relations"}

    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 获取当前所有 chunk 的当前 relations
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"搜索失败: {resp.status_code}"}

        points = resp.json()["result"]["points"]
        if not points:
            return {"ok": False, "error": f"未找到 doc_id={doc_id} 的记录"}

        # 取第一个 chunk 的 relations 作为基准，做合并
        base_relations = list(points[0].get("payload", {}).get("relations", []))
        for ar in add_relations:
            if ar not in base_relations:
                base_relations.append(ar)
        for rr in remove_relations:
            if rr in base_relations:
                base_relations.remove(rr)

        # 用 set_payload API 批量更新所有该 doc 的 chunk
        all_ids = [p["id"] for p in points]
        put_resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/payload",
            json={"payload": {"relations": base_relations}, "points": all_ids},
            timeout=10
        )
        if put_resp.status_code != 200:
            return {"ok": False, "error": f"更新失败: {put_resp.status_code}"}

        return {"ok": True, "updated": len(points), "doc_id": doc_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_by_doc_id(
    doc_id: str,
    collection: str = DEFAULT_COLLECTION,
) -> dict:
    """
    按 doc_id 查找所有 chunk。

    返回:
        {"ok": true, "doc_id": "...", "chunks": [{...}, ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"搜索失败: {resp.status_code}"}

        points = resp.json()["result"]["points"]
        chunks = []
        for p in points:
            payload = p.get("payload", {})
            chunks.append({
                "text":            payload.get("text", ""),
                "title":           payload.get("title", ""),
                "source":          payload.get("source", "未知"),
                "chunk_index":     payload.get("chunk_index", 0),
                "content_type":    payload.get("content_type", ""),
                "domain":          payload.get("domain", []),
                "temporal_nature": payload.get("temporal_nature", ""),
                "epistemic_status":payload.get("epistemic_status", ""),
                "lifecycle":       payload.get("lifecycle", ""),
                "project_source":  payload.get("project_source", ""),
                "udc_code":        payload.get("udc_code", ""),
                "trust_score":     payload.get("trust_score", 3),
                "is_canonical":    payload.get("is_canonical", True),
                "is_archived":     payload.get("is_archived", False),
                "needs_review":    payload.get("needs_review", False),
                "relations":       payload.get("relations", []),
                "keywords":        payload.get("keywords", []),
                "auto_summary":    payload.get("auto_summary", ""),
                "timeline":        payload.get("timeline", {}),
                "origin":          payload.get("origin", {}),
                "stats":           payload.get("stats", {}),
            })

        return {"ok": True, "doc_id": doc_id, "total": len(chunks), "chunks": chunks}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_doc_ids(
    collection: str = DEFAULT_COLLECTION,
    limit: int = 200,
) -> dict:
    """
    获取集合中的去重 doc_id 列表（用于知识中枢管理）。

    返回:
        {"ok": true, "doc_ids": ["xxx", "yyy", ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 先获取总数
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        total_pts = info.json()["result"]["points_count"] if info.status_code == 200 else 0

        if total_pts == 0:
            return {"ok": True, "doc_ids": []}

        # 分页 scroll：每批 1000，取足去重 doc 或遍历完所有 points
        scroll_limit = 1000
        offset = 0
        seen = set()
        doc_ids = []
        while True:
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "with_payload": True, "with_vector": False},
                timeout=30
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break

            for p in batch:
                did = p.get("payload", {}).get("doc_id", "")
                if did and did not in seen:
                    seen.add(did)
                    doc_ids.append(did)
                    if len(doc_ids) >= limit:
                        break
            offset += len(batch)
            if len(doc_ids) >= limit:
                break
            if len(doc_ids) >= limit:
                break

        return {"ok": True, "doc_ids": doc_ids, "total_unique": len(doc_ids)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_documents(collection: str = DEFAULT_COLLECTION,
                  page: int = 1,
                  page_size: int = 20,
                  needs_review: bool = None) -> dict:
    """
    列出知识库中的去重文档（分页）。
    按 doc_uid 去重，每个文档取 chunk_index=0 的元数据作为代表。

    参数：
        needs_review: 如果为 True/False，只返回对应标记的文档；如果为 None，返回所有文档

    返回：
        {
            "ok": True,
            "documents": [...],
            "total": N,
            "page": 1,
            "page_size": 20,
            "total_pages": N,
        }
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 获取总数
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        if info.status_code != 200:
            return {"ok": False, "error": f"集合 {collection} 不存在"}
        total_pts = info.json()["result"]["points_count"]

        if total_pts == 0:
            return {
                "ok": True,
                "documents": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

        # 分页 scroll 收集去重文档（取每个 doc_uid 的第一个 chunk）
        scroll_limit = 1000
        offset = 0
        seen = {}
        # seen[doc_uid] = {metadata from first chunk}

        # 构建 filter（如果 needs_review 不是 None）
        scroll_filter = None
        if needs_review is not None:
            scroll_filter = {
                "must": [
                    {"key": "needs_review", "match": {"value": bool(needs_review)}}
                ]
            }

        while True:
            scroll_body = {
                "limit": scroll_limit,
                "offset": offset,
                "with_payload": True,
                "with_vector": False,
            }
            if scroll_filter:
                scroll_body["filter"] = scroll_filter

            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json=scroll_body,
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break

            for p in batch:
                pl = p.get("payload", {})
                did = pl.get("doc_uid", "")
                if not did:
                    continue
                if did not in seen:
                    seen[did] = {
                        "doc_uid": did,
                        "title": pl.get("title", "") or pl.get("source", "未知"),
                        "source": pl.get("source", ""),
                        "content_type": pl.get("content_type", ""),
                        "domain": pl.get("domain", []),
                        "temporal_nature": pl.get("temporal_nature", ""),
                        "epistemic_status": pl.get("epistemic_status", ""),
                        "trust_score": pl.get("trust_score", 3),
                        "is_personal": pl.get("is_personal", False),
                        "chunk_count": 1,
                        "created_at": pl.get("created_at", ""),
                    }
                else:
                    seen[did]["chunk_count"] += 1

            offset += len(batch)
            if offset >= total_pts:
                break

        # 转成列表，按 created_at 降序
        docs = list(seen.values())
        docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)

        total = len(docs)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "ok": True,
            "documents": docs[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_document(doc_uid: str, collection: str = DEFAULT_COLLECTION) -> dict:
    """
    获取指定文档的所有分块。
    返回：
        {"ok": True, "doc_uid": "...", "chunks": [{text, ...}, ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 使用 scroll + filter 获取该 doc_uid 的所有 points
        all_points = []
        scroll_limit = 1000
        offset = 0

        while True:
            filter_obj = {"must": [{"key": "doc_uid", "match": {"value": doc_uid}}]}
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "filter": filter_obj,
                      "with_payload": True, "with_vector": False},
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break
            all_points.extend(batch)
            offset += len(batch)
            if len(batch) < scroll_limit:
                break

        if not all_points:
            return {"ok": False, "error": f"文档 {doc_uid} 不存在"}

        chunks = []
        for p in all_points:
            pl = p.get("payload", {})
            chunks.append({
                "chunk_index": pl.get("chunk_index", 0),
                "text": pl.get("text", ""),
                "title": pl.get("title", ""),
                "source": pl.get("source", ""),
                "content_type": pl.get("content_type", ""),
                "domain": pl.get("domain", []),
                "images": pl.get("images", []),
            })

        chunks.sort(key=lambda c: c["chunk_index"])
        return {"ok": True, "doc_uid": doc_uid, "chunks": chunks}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_document(doc_uid: str, collection: str = DEFAULT_COLLECTION) -> dict:
    """
    删除指定文档的所有分块。
    返回：
        {"ok": True, "deleted": N}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 先获取所有匹配的点 ID
        point_ids = []
        scroll_limit = 1000
        offset = 0

        while True:
            filter_obj = {"must": [{"key": "doc_uid", "match": {"value": doc_uid}}]}
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "filter": filter_obj,
                      "with_payload": False, "with_vector": False},
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break
            point_ids.extend([p["id"] for p in batch])
            offset += len(batch)
            if len(batch) < scroll_limit:
                break

        if not point_ids:
            return {"ok": False, "error": f"文档 {doc_uid} 不存在"}

        # 批量删除（每批 1000）
        deleted = 0
        for i in range(0, len(point_ids), 1000):
            batch_ids = point_ids[i:i+1000]
            del_resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/delete",
                json={"points": batch_ids},
                timeout=30,
            )
            if del_resp.status_code == 200:
                deleted += len(batch_ids)

        return {"ok": True, "deleted": deleted, "doc_uid": doc_uid}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def update_document(doc_uid: str, metadata: dict,
                   collection: str = DEFAULT_COLLECTION) -> dict:
    """
    更新指定文档所有分块的元数据。
    metadata 中的字段会覆盖所有分块的对应字段。

    返回：
        {"ok": True, "updated": N}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 先获取所有匹配的点
        all_points = []
        scroll_limit = 1000
        offset = 0

        while True:
            filter_obj = {"must": [{"key": "doc_uid", "match": {"value": doc_uid}}]}
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "filter": filter_obj,
                      "with_payload": True, "with_vector": True},
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break
            all_points.extend(batch)
            offset += len(batch)
            if len(batch) < scroll_limit:
                break

        if not all_points:
            return {"ok": False, "error": f"文档 {doc_uid} 不存在"}

        # 更新 payload
        updated = 0
        for p in all_points:
            pid = p["id"]
            vector = p.get("vector", [])
            payload = p.get("payload", {})
            payload.update(metadata)
            # 写回 Qdrant（覆盖原 point）
            requests.put(
                f"{QDRANT_URL}/collections/{collection}/points",
                json={
                    "points": [{"id": pid, "vector": vector, "payload": payload}]
                },
                timeout=30,
            )
            updated += 1

        return {"ok": True, "updated": updated, "doc_uid": doc_uid}

    except Exception as e:
        return {"ok": False, "error": str(e)}
