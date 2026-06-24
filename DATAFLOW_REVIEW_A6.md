# 数据流完整性审查报告（A6）
**审查时间**: 2026-06-24  
**审查角度**: 数据流完整性——追踪数据从摄入到检索再到生成的完整链路  
**审查范围**: ingest_pipeline.py, kb_query.py, search_engine.py, classify_pipeline.py

---

## 执行摘要

✅ **数据流入库完整** — 摄入阶段的10个步骤正确将数据写入Qdrant  
⚠️ **搜索结果字段不完整** — 搜索结果缺少4个关键字段  
⚠️ **RAG阶段信息损失** — answer()函数无法访问confidence等字段  
✅ **数据结构一致** — 摄入和搜索使用相同的数据结构  

---

## 1. 数据流映射

### 1.1 摄入阶段（ingest_pipeline.py + kb_query.py）

```
文件/文本
  → _step_read_content()     [读取文本]
  → _step_dedup()           [去重检查]
  → _step_extract_images()   [提取图片]
  → _step_chunk()            [分块]
  → _step_generate_sparse_vectors() [生成稀疏向量]
  → _step_embed()            [生成稠密向量]
  → _step_pre_store_hooks()  [预存储钩子]
  → _step_build_payloads()   [构建payload]
  → _step_write_qdrant()    [写入Qdrant]
  → _step_log_ingest()      [写入日志]
```

**Qdrant Payload 结构** (`ingest_pipeline.py:_build_point()`):
```python
{
    "text": chunk,
    "title": m["title"],
    "source": m.get("source", "unknown"),
    "chunk_index": i,
    "total_chunks": total_chunks,          # ✅ 存储
    "doc_id": doc_id,
    "doc_uid": doc_id,
    "content_hash": full_text_hash,
    "images": m["valid_images"],
    # 分面字段
    "content_type": m["content_type"],
    "domain": m["domain"],
    "temporal_nature": m["temporal_nature"],
    "epistemic_status": m["epistemic_status"],
    # 生命周期
    "lifecycle": m["lifecycle"],
    "project_source": m["project_source"],
    "udc_code": m["udc_code"],
    # 知识管理
    "knowledge_type": m["knowledge_type"],
    "is_personal": m["is_personal"],
    "trust_score": m["trust_score"],
    "tags": m["tags"],
    "is_canonical": m["is_canonical"],
    "relations": m["relations"],
    "keywords": m["keywords"],
    "auto_summary": m["auto_summary"],
    # 时间线
    "timeline": {...},
    "origin": {...},
    "stats": {"access_count": 0, "starred": False},
    # 内容创作
    "target_platform": m["target_platform"],
    "related_product": m["related_product"],
    "version": m["version"],
    # 系统
    "language": m["language"],
    "access_level": m["access_level"],
    "batch_id": m["batch_id"],
    "is_archived": False,
    "needs_review": m["needs_review"],        # ✅ 存储
    # 字段来源 + 置信度
    "field_sources": m["field_sources"],       # ✅ 存储
    "confidence": m["confidence"],             # ✅ 存储（值来自overall_confidence）
    # 预留扩展
    "ext_text1": None, ... "ext_date3": None, # ✅ 存储
}
```

### 1.2 搜索阶段（search_engine.py）

```
查询文本
  → _embed()                [生成查询向量]
  → _build_qdrant_filter()  [构建过滤条件]
  → _query_qdrant_rrf()    [执行RRF混合查询]
  → 整理结果                [构建chunks列表]
  → 分组去重                [按doc_id分组]
```

**搜索结果结构** (`search_engine.py:search()`):
```python
{
    "ok": True,
    "query": query,
    "total": len(chunks),
    "chunks": [{
        "text": payload.get("text", ""),
        "title": payload.get("title", ""),
        "source": payload.get("source", "未知"),
        "score": round(r.get("score", 0), 4),
        "chunk_index": payload.get("chunk_index", 0),
        "doc_id": payload.get("doc_id", ""),
        "content_hash": payload.get("content_hash", ""),
        "doc_uid": payload.get("doc_uid", ""),
        "images": payload.get("images", []),
        # 分面字段
        "content_type": payload.get("content_type", "knowledge"),
        "domain": payload.get("domain", []),
        "temporal_nature": payload.get("temporal_nature", "timeboxed"),
        "epistemic_status": payload.get("epistemic_status", "unverified"),
        # 普通字段
        "lifecycle": payload.get("lifecycle", ""),
        "project_source": payload.get("project_source", ""),
        "udc_code": payload.get("udc_code", ""),
        # 知识管理
        "is_personal": payload.get("is_personal", False),
        "trust_score": payload.get("trust_score", 3),
        "knowledge_type": payload.get("knowledge_type", ""),
        "tags": payload.get("tags", []),
        "is_canonical": payload.get("is_canonical", True),
        "relations": payload.get("relations", []),
        "keywords": payload.get("keywords", []),
        "auto_summary": payload.get("auto_summary", ""),
        # 分组字段
        "timeline": payload.get("timeline", {}),
        "origin": payload.get("origin", {}),
        "stats": payload.get("stats", {}),
        # 内容创作
        "target_platform": payload.get("target_platform", "none"),
        "related_product": payload.get("related_product", ""),
        "version": payload.get("version", ""),
        # 系统字段
        "language": payload.get("language", "zh"),
        "access_level": payload.get("access_level", "private"),
        "batch_id": payload.get("batch_id", ""),
        "is_archived": payload.get("is_archived", False),
        # ❌ 缺失字段：
        # - total_chunks
        # - needs_review
        # - field_sources
        # - confidence
        # - ext_text1-ext_text5, ext_num1-ext_num3, ...
    }, ...]
}
```

### 1.3 RAG阶段（search_engine.py:answer()）

```
搜索结果（chunks）
  → _dedup_chunks()         [去重+质量过滤]
  → _build_synthesis_prompt() [构建合成提示词]
  → _call_llm_api()         [调用LLM合成]
  → _renumber_citations()   [重编号引用]
  → _render_report_html()    [渲染HTML报告]
```

**问题**: `answer()`函数使用的`chunks`缺少`confidence`、`needs_review`等字段，无法在合成时使用这些信息。

---

## 2. 发现的问题

### 🔴 P1: 搜索结果缺少关键字段

**位置**: `search_engine.py:search()` 函数（第334-377行）

**问题描述**:  
搜索结果（`chunks`）缺少以下存储在Qdrant中的字段：
1. `total_chunks` - 文档总块数
2. `needs_review` - 是否需要人工审核
3. `field_sources` - 字段来源（用于调试/审计）
4. `confidence` - 整体置信度
5. 扩展字段（`ext_text1`-`ext_text5`等）

**影响**:
- `answer()`函数无法访问`confidence`信息，可能在合成时无法优先考虑高置信度结果
- UI无法显示`needs_review`状态
- 无法在搜索结果中显示文档完整性信息（`total_chunks`）

**修复方案**:
在`search()`函数的`chunks.append()`中添加缺失的字段。

**优先级**: P1

---

### 🟡 P2: 字段名称不一致

**位置**: `kb_query.py` 第286行 vs `ingest_pipeline.py` 第153行

**问题描述**:
- `kb_query.py`中使用`overall_confidence`作为键名
- `ingest_pipeline.py`中读取`confidence_overall`，但存储为`confidence`

**实际代码**:
```python
# kb_query.py:286
base_meta["confidence_overall"] = state["overall_confidence"]

# ingest_pipeline.py:83
"confidence": base_meta.get("confidence_overall", None)

# ingest_pipeline.py:153
"confidence": m["confidence"],
```

**结论**: 实际代码是正确的，`confidence_overall`是临时键名，`confidence`是Qdrant中的最终键名。但容易引起混淆。

**修复方案**:
考虑统一命名，或在文档中明确说明。

**优先级**: P2

---

### 🟢 P3: 扩展字段未使用

**位置**: `ingest_pipeline.py` 第156-160行

**问题描述**:  
扩展字段（`ext_text1`-`ext_text5`等）已定义在payload结构中，但：
1. 没有地方设置这些字段
2. 搜索结果中不返回这些字段
3. 没有使用这些字段的功能

**影响**: 占用存储空间，但无功能影响。

**修复方案**:
1. 如果不需要这些字段，从payload结构中移除
2. 如果需要，添加设置和使用这些字段的功能

**优先级**: P3

---

## 3. 数据流完整性评估

| 阶段 | 完整性 | 说明 |
|------|--------|------|
| 摄入→Qdrant | ✅ 完整 | 所有字段正确存储 |
| Qdrant→搜索结果 | ⚠️ 不完整 | 缺少5个字段 |
| 搜索结果→RAG | ⚠️ 不完整 | 缺少confidence等字段 |
| RAG→HTML报告 | ✅ 完整 | 正确使用搜索结果 |

---

## 4. 修复计划

### 4.1 立即修复（P1）

**任务**: 在`search()`函数中添加缺失的字段

**文件**: `search_engine.py`

**修改位置**: 第334-377行（`chunks.append()`部分）

**添加字段**:
```python
"total_chunks":    payload.get("total_chunks", 0),
"needs_review":    payload.get("needs_review", False),
"field_sources":   payload.get("field_sources", {}),
"confidence":      payload.get("confidence", None),
```

### 4.2 后续优化（P2-P3）

1. 统一字段命名规范
2. 清理未使用的扩展字段
3. 在`answer()`函数中使用`confidence`信息优化合成

---

## 5. 测试建议

1. **单元测试**: 测试`search()`函数是否返回所有字段
2. **集成测试**: 测试从摄入到搜索的完整数据流
3. **UI测试**: 测试搜索结果页面是否显示`needs_review`状态

---

## 6. 审查结论

数据流完整性存在**1个P1问题**（搜索结果缺少关键字段），需要立即修复。修复后，数据流将完全完整，从摄入到RAG的每个阶段都能访问所需的所有字段。

**建议**: 优先修复P1问题，然后继续其他阶段的审查。
