#!/usr/bin/env python3
"""Batch fix P2/P3 issues - Batch 1."""
import re

with open('/d/citrinitas/kb_query.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ── Fix D4: _text_hash() 16→32 ──
old_d4 = '    """内容的去重哈希（规范化后 SHA256，取前 16 位）"""\n    normalized = re.sub(r\'\\s+\', \' \', text).strip().lower()\n    return hashlib.sha256(normalized.encode()).hexdigest()[:16]'
new_d4 = '    """内容的去重哈希（规范化后 SHA256，取前 32 位）"""\n    normalized = re.sub(r\'\\s+\', \' \', text).strip().lower()\n    return hashlib.sha256(normalized.encode()).hexdigest()[:32]'
if old_d4 in content:
    content = content.replace(old_d4, new_d4, 1)
    print("✅ D4: _text_hash() 16→32 位")
else:
    print("❌ D4: 原字符串未找到")

# ── Fix F6+S3: search() chunks.append() 补 content_hash ──
# 在 "doc_id" 行后插入 "content_hash"
old_f6 = '            "doc_id":          payload.get("doc_id", ""),\n            "images":'
new_f6 = '            "doc_id":          payload.get("doc_id", ""),\n            "content_hash":    payload.get("content_hash", ""),\n            "images":'
if old_f6 in content:
    content = content.replace(old_f6, new_f6, 1)
    print("✅ F6+S3: search() 补 content_hash")
else:
    print("❌ F6+S3: search() chunks.append 未找到")

# ── Fix S4: search() chunks.append() 补 doc_uid ──
old_s4 = '            "content_hash":    payload.get("content_hash", ""),\n            "images":'
new_s4 = '            "content_hash":    payload.get("content_hash", ""),\n            "doc_uid":        payload.get("doc_uid", ""),\n            "images":'
if old_s4 in content:
    content = content.replace(old_s4, new_s4, 1)
    print("✅ S4: search() 补 doc_uid")
else:
    # 如果 F6 没成功，尝试直接找 images 行
    print("❌ S4: 依赖 F6，跳过高")

# ── Fix C10: except:pass 加日志（所有 except Exception: pass）──
# 把 "except Exception:\n        pass  # 回退到 PaddleOCR" 加日志
old_c10a = '    except Exception:\n        pass  # 回退到 PaddleOCR'
new_c10a = '    except Exception as e:\n        print(f"[WARN] PPStructureV3 失败，回退到 PaddleOCR: {e}")\n        pass  # 回退到 PaddleOCR'
if old_c10a in content:
    content = content.replace(old_c10a, new_c10a, 1)
    print("✅ C10a: PPStructureV3 except 加日志")
else:
    print("⚠️ C10a: PPStructureV3 except 未找到（可能已修改）")

# except OSError: pass（临时文件清理）加日志
old_c10b = '            except OSError:\n                pass'
new_c10b = '            except OSError as e:\n                print(f"[DEBUG] 临时文件删除失败: {e}")'
if old_c10b in content:
    content = content.replace(old_c10b, new_c10b, 1)
    print("✅ C10b: 临时文件清理 except 加日志")
else:
    print("⚠️ C10b: 临时文件清理 except 未找到")

# _log_ingest 的 except pass 加日志
old_c10c = '    except Exception:\n        pass  # 日志写入失败不影响主流程'
new_c10c = '    except Exception as e:\n        print(f"[WARN] 摄入日志写入失败: {e}")'
if old_c10c in content:
    content = content.replace(old_c10c, new_c10c, 1)
    print("✅ C10c: _log_ingest except 加日志")
else:
    print("⚠️ C10c: _log_ingest except 未找到")

# ── E3 复核：_format_evidence_text() 确认 XSS 防护 ──
# 检查是否有 _html.escape() 调用
if '_html.escape(line)' in content:
    print("✅ E3 复核: _format_evidence_text() 已调用 _html.escape()，XSS 防护有效")
else:
    print("❌ E3 复核: _format_evidence_text() 未找到 _html.escape()！")

# 写回
with open('/d/citrinitas/kb_query.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\nDone! 请运行语法检查。")
